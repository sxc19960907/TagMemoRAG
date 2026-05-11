# brainstorm: 浪潮RAG 产品说明书语义检索引擎（生产级路线图）

## Goal

构建一个**生产级、分阶段演进**的语义检索引擎，用于客服 RAG 系统长期运行。采用**浪潮检索算法（WAVE-RAG）**：语义拓扑图组织知识块，用户查询作为波源沿图传播能量，干涉汇聚后取 Top-K。

### 目标形态

- v1 交付：**单节点容器化生产部署**，具备可观测、安全、热更新、多知识库能力
- 架构预留向 **多副本 HA / 向量后端切换 / 多租户** 演进的接口，但 v1 不实现
- **分阶段交付**：M0 功能核心 → M1 运维基础 → M2 零停机+多KB → M3 质量回归 → M4 观测增强

### 非功能性需求（NFR）

| 维度 | v1 目标 | 归属里程碑 |
|------|---------|-----------|
| 延迟 p95 | < 50ms @ 1000 节点（CPU） | M0 |
| 延迟 p99 | < 150ms @ 1000 节点 | M0 |
| 吞吐 | 50 QPS（嵌入缓存命中后） | M2 |
| 可用性 | 99.5%（不含计划维护） | M2 |
| Rebuild | 0 停机（单机内存 double-buffer） | **M0** |
| Rebuild | 0 停机（多副本协调） | M2 |
| 冷启动 | < 10s（含模型加载 + 图加载） | M1 |
| 检索质量 | precision@5 ≥ 0.8 / MRR ≥ 0.75 | M3 |
| 可观测 | Prometheus metric / JSON log / OTel hooks | M1/M4 |

### 参考源

- VCPToolBox 的 `DreamWaveEngine` (Plugin/AgentDream/DreamWaveEngine.js) — 原始浪潮算法（时间桶 + 种子→共振→级联→深渊向量合并）
- `浪潮RAG_产品说明书_详细设计说明书.md` — 为目标场景（产品说明书）重新设计的图传播版浪潮算法

## What I already know

### 设计文档中的架构（图传播版浪潮）
- **文档分块器**：按标题层级切分 Markdown/PDF，保留元数据（标题路径、层级、行号）
- **向量化引擎**：BAAI/bge-small-zh-v1.5 (384维)，CPU 可运行
- **语义拓扑图**：NetworkX 无向图，节点=知识块+向量，边=语义相似度 + 结构奖励（父子/兄弟/连续）
- **波扩散检索**：query → embed → top-3 源节点 → 沿边传播(decay=0.7, steps=3) → 干涉取最大值 → top-K
- **联想锚定**：手动标记关键节点，boost 振幅
- **API**：FastAPI (`POST /search`, 锚点 CRUD, 图信息)

### VCPToolBox DreamWaveEngine 原始浪潮算法（时间桶版）
- **三阶段**：近期涟漪(L0→L1共振→L2下探) → 中期涟漪 → 深渊浪潮（向量合并搜索）
- **3/5/7 原则**：短记忆 k=3，中 k=5，长 k=7
- **共振桥梁**：被多个种子重复命中的记忆作为 L1
- **测地线重排 (V8)**：tagBoost="0.6+" 触发，过采样 2×k
- **深渊浪潮**：所有 L1/L2 向量归一化求和 → 合成"浪潮向量"搜索深远记忆
- **防爆 Token**：逐组截断，确保不超上下文窗口

### 当前项目状态
- 项目名：`tagmemorag`，Python 3.11+，hatchling 构建
- `src/tagmemorag/__init__.py` 和 `tests/__init__.py` 为空文件
- 依赖尚未添加

### 两个版本的"浪潮"核心差异
| 维度 | 设计文档（图传播版） | VCPToolBox（时间桶版） |
|------|---------------------|----------------------|
| 知识组织 | 静态语义拓扑图 (NetworkX) | 动态时间桶 (recent/mid/deep) |
| 传播方式 | 图边权重衰减传播 | 向量召回 + 共振检测 + 级联 |
| 波源 | query 的 top-3 相似节点 | 随机抽取的种子记忆 |
| 应用场景 | 产品说明书检索 | AI Agent 记忆联想 |
| 语言/平台 | Python/FastAPI | Node.js |

## Decision (ADR-lite)

**Context**：需要在图传播版（设计文档）和时间桶版（VCPToolBox DreamWaveEngine）之间选择架构方向。目标场景是客服 RAG 系统。

**Decision**：MVP 采用**纯图传播版**。客服知识库是结构化静态文档（说明书/FAQ），有明确章节层级，不需要时间桶。图的结构边（父子/兄弟）天然支持跨章节检索这一客服核心需求。锚点系统对安全/紧急类客服回答特别有价值。

**Consequences**：VCPToolBox 的共振桥梁、深渊向量合并等机制暂不引入，可在后续版本作为补充召回通道。时间桶模式整体搁置。

### Decision: 波干涉聚合方式 = max（可配置）

**Context**：设计文档 3.4.3 写"多波源到达同一节点取最大值，亦可实验求和"。max 与 sum 对排序行为影响巨大，MVP 必须锁定默认值。

**Decision**：默认 **max**。实现里暴露聚合函数参数 `aggregate: Literal["max", "sum"] = "max"`，`config.yaml`、`POST /search` 均可覆盖。

**Rationale**：
- 分数域稳定：max 输出恒在 `[0, 1]`，sum 上限随图连通度漂移，跨数据集需要重调 `amplitude_cutoff`
- 贴合跨章节并列召回目标（"蒸汽很小" → 蒸汽+E05+清洗，三条独立强链路，不需要共振叠加）
- 锚点 boost 在 max 下可解释性强；sum 下 boost × 多源累加过分放大
- 物理类比不成立：标量强度没有相位，"求和"其实不是干涉

**Consequences**：预留 sum 开关便于后续 A/B；MVP 调参和验收只基于 max 路径。

### Decision: 锚点稳定标识 = anchor_key + reconcile

**Context**：设计文档 `set_anchor(node_id, ...)` 用 NetworkX int 节点编号，每次 `POST /rebuild` 或文档修订后 node_id 全部重新分配，已设锚点全部失效。客服场景锚点是人工维护的高价值资产（紧急停机、故障码），必须跨重建保留。

**Decision**：双轨设计。
- 对外 API 暴露 `anchor_key: str`（稳定标识），格式 `sha256(path_joined + "|" + header + "|" + text[:80])[:12]`
- 内部维护 `anchor_key → node_id` 映射表，随图一同持久化
- `rebuild` 后跑一次 reconcile：
  1. 先按 `anchor_key` 精确匹配新图节点（路径+标题+前80字未变的块直接命中）
  2. 未命中的锚点用原锚点文本 embedding 在新图做 top-1 最近邻匹配，余弦 > 0.85 视为成功
  3. 仍未命中的锚点放入 `unresolved_anchors` 列表，通过 `GET /graph_info` 或 rebuild 响应返回，要求人工重配
- API 层面 `POST /anchor` 接收 `{node_id, label, boost}`，服务端自动计算 `anchor_key` 并存储；`DELETE /anchor` 和 `GET /anchor` 以 `anchor_key` 为主键

**Rationale**：
- 用户不需要关心 node_id 不稳定性
- 两级 reconcile（哈希精确 + 向量近邻）覆盖"文档微调"和"局部重写"两类变更
- unresolved 列表使失效锚点可见，避免静默丢失

**Consequences**：锚点存储结构额外一个 `anchor_key` 字段；rebuild 比单纯重建图多一步 reconcile（代价 = O(锚点数) 次 embedding 查询，通常 <100 个，可忽略）；`AnchorSystem` 模块职责从纯 CRUD 扩展到"持久化 + reconcile"。

### Decision: 持久化 = 分层 + 接口化（MVP 用 JSON+NPZ，不用 pickle）

**Context**：原设计文档提 `graph.pkl`，但目标是"成熟 RAG 系统"，需要跨版本稳定、可增量、可换向量后端、跨语言可读、事务安全。pickle 在这些维度全部不合格。

**Decision**：存储按三个关注点分层，每层一个抽象接口，MVP 用 JSON/NPZ 实现，后续替换 Faiss/Qdrant/pgvector 零改动上层。

- 抽象层（`src/tagmemorag/storage/base.py`）：
  - `GraphStore`：`save(graph) / load() -> graph`，预留 `add_nodes / remove_nodes`（MVP `NotImplementedError`）
  - `VectorStore`：`add(ids, vecs) / search(query_vec, k) / get(id) -> vec`，预留 `delete / update`
  - `AnchorStore`：锚点 CRUD + `reconcile(old_anchors, new_graph, embedder) -> (remapped, unresolved)`
- MVP 实现：
  - `JsonGraphStore` → `data/{kb}/graph.json`（节点元数据 + 边列表，不含向量）
  - `NpzVectorStore` → `data/{kb}/vectors.npz`（`ids: int[N]`, `vecs: float32[N, 384]`）
  - `JsonAnchorStore` → `data/{kb}/anchors.json`
  - `data/{kb}/meta.json`：`schema_version / model_name / model_dim / built_at / chunk_count / aggregate_default`
- 写入策略：所有文件一律 `write-to-tmp + os.replace` 原子落盘，避免坏文件
- 加载策略：`meta.json.schema_version` 不匹配时拒绝加载，由迁移脚本处理

**Rationale**：
- 版本兼容：JSON + schema_version，老库可写迁移
- 增量预留：接口签名就绪，MVP 只实现"一次性构图"，后续加 `add_nodes` 无需改上层
- 向量后端可换：换 Faiss/Qdrant 只需新写一个 `VectorStore` 实现
- 跨语言：JSON 图 + numpy npz，客服侧 Node/Go 可直接读元数据
- 事务安全：原子替换
- 可测试：JSON 夹具可以手写单测用例
- 避开 pickle 的跨版本脆弱性和反序列化攻击面

**Consequences**：
- 模块数从 8 增加到 11（新增 `storage/base.py` + 三个 store 实现）
- 比 pickle 多约 150 行，首次加载多 O(N) 的 zip 合并（<100ms/万节点）
- 增量更新本身仍在 Out of Scope，但接口与目录结构已为后续预留

### Decision: 锚点传播增益 = 默认关，开关可配

**Context**：设计文档 3.5 提到"锚点节点被激活时传播振幅也乘以 boost（可选）"。开启会让锚点像"超导路径"把整个邻域拉高，关闭则锚点只在波源阶段生效。

**Decision**：默认 **关**（`propagation_boost: 1.0`）。`config.yaml` 和 `POST /search` 可覆盖设 >1.0 开启。

**Rationale**：默认行为要可预测、验收可复现；"紧急停机扩散到整个安全主题区"是真实但需调参的需求，留配置项不承诺默认开启。

**Consequences**：波传播内层循环多一次 `if node in anchors: amp *= propagation_boost`，成本可忽略。

### Decision: 生产级形态 = 单节点 + HA 兼容架构

**Context**：目标是"生产环境落地"，但从 MVP 到对外 SaaS 级成本差 5 倍。需要锁定 v1 形态。

**Decision**：v1 交付**单节点容器化**（1-10 QPS，单 Pod / docker-compose），架构接口预留多副本扩展（共享存储 + rebuild 协调器）。v1 不实现 HA / 多租户 / 分布式追踪，但模块边界不挡后续升级。

**Rationale**：
- 客服场景初期流量可控，单节点够用
- 90% 的"生产级质量"来自可观测 / 安全 / 零停机 / 回归 — 这些都可以在单节点做到
- HA 真正需要时（>50 QPS 或 SLA > 99.5%）再加，避免过早引入 etcd / 分布式锁

**Consequences**：v1 存储用本地文件；v2 要升 HA 时需换共享卷或对象存储 + rebuild leader election。接口已按此预留。

### Decision: 分阶段里程碑

**Context**：生产级交付不是一口气做完。需要定义可独立上线的阶段。

**Decision**：5 个里程碑，每个里程碑结束即可上线（产出递增而非重做）。

| 里程碑 | 范围 | 交付物 | 预估 |
|--------|------|--------|------|
| **M0 功能核心** | 波算法 + 锚点 + 存储分层 + 基础 API/CLI + 单机内存 double-buffer rebuild | 单元+E2E 测试通过，本地可跑，单机零停机热更 | 本任务 |
| **M1 运维基础** | Dockerfile/compose / JSON 日志 / `/health`,`/ready` / 优雅关闭 / 配置环境变量化 / 模型 warm-up | 镜像可部署 | 独立任务 |
| **M2 零停机 + 多KB** | API key + 限流 / 多副本 rebuild 协调器（leader election）/ 多 KB 目录隔离（`data/{kb}/`）/ 查询缓存 | 支持多副本 HA 与多产品线 | 独立任务 |
| **M3 质量回归** | Eval 框架（标注集 + precision@k/recall@k/MRR）/ CI 回归门禁 / 错误码枚举 | 退化自动告警 | 独立任务 |
| **M4 观测增强** | Prometheus `/metrics` / OTel traces hook / 结构化查询审计日志 | 可接公司监控栈 | 独立任务 |
| **post-v1** | HA 多副本 / 向量后端切 Faiss/Qdrant / SSO/RBAC | 按需启动 | 不在路线图 |

**Rationale**：
- 每个里程碑都是一个独立 Trellis 任务，本任务只做 M0
- M1-M4 在 M0 架构上叠加，不需要改核心算法
- 依赖链：M0 → (M1, M2 并行) → M3 → M4

**Consequences**：本 PRD 的 `Requirements / Acceptance Criteria / DoD` 只约束 M0；M1-M4 各自新建 task 时从本 PRD 的 Milestone 段抽取并展开。

### Decision: M0 的 `POST /rebuild` = 单机内存 double-buffer（零停机）

**Context**：`POST /rebuild` 期间如何处理并发的 `/search` 请求，决定了 v1 是否"像生产级"。候选方案从简陋到完备：阻塞 503 / 读写锁 / 内存 double-buffer / 干脆不做。

**Decision**：M0 直接实现**单机内存 double-buffer**。
- 全局 `AppState` 单例持有 `current_graph`、`current_stores`、`current_anchors` 的原子引用（`threading.local` + volatile 指针）
- `POST /rebuild` 在后台线程（或 `asyncio.to_thread`）读新文档、构新图、reconcile 锚点 — 全程不影响 `current_graph`
- 新图构建成功后，一条 CAS 语义的指针替换：`AppState.current = new_state`；旧图引用由 GC 回收
- 新图构建失败：保留旧图，返回 `{code: "REBUILD_FAILED", detail: ...}`，线上服务连续可用
- `POST /rebuild` 立即返回 `{task_id, status: "running"}`，异步 `GET /rebuild/{task_id}` 查状态
- 同一时间只允许一个 rebuild（`AppState.rebuild_lock`），第二个并发请求返回 `{code: "REBUILD_IN_PROGRESS"}`

**Rationale**：
- 30 行额外代码换来真零停机 rebuild
- M2 升级 HA 时，"跨进程共享存储 + leader election"在此架构上叠加，M0 不白费
- NFR 表里 "Rebuild 0 停机" 可以从 M2 提前到 M0 达成（单节点范围）
- 峰值内存 × 2 但 <50MB，在 4GB 环境下无压力

**Consequences**：
- `AppState` 的所有访问必须通过单一 accessor 拿引用后不再持有过久（避免 rebuild 后旧图不被 GC）
- `/search` 的 trace_id / log 记录图 `build_id`，便于事后复盘某次查询用的是哪版图
- NFR "Rebuild 0 停机" 归属从 M2 改为 M0

## Assumptions (temporary)

* 第一阶段数据集 < 1万节点，全量计算语义边即可（不需要 Faiss 近似）
* 嵌入模型使用 BAAI/bge-small-zh-v1.5（设计文档指定）
* MVP 只做 Markdown/TXT 输入，PDF 后续再支持
* 交付形态为 FastAPI REST API（无 Web UI），方便客服系统对接
* 本任务（M0）只交付单节点本地可跑的功能核心，容器化/观测/安全/回归拆到 M1-M4

## Open Questions

* （M0 范围内无阻塞问题）

## Requirements (M0 — 功能核心)

### 模块清单

| # | 模块 | 文件 | 职责 |
|---|------|------|------|
| 1 | DocumentParser | `src/tagmemorag/parser.py` | 按标题层级切分 MD/TXT，保留 header/path/level/line 元数据 |
| 2 | Embedder | `src/tagmemorag/embedder.py` | BGE-small-zh-v1.5 向量化，384维归一化 |
| 3 | GraphBuilder | `src/tagmemorag/graph_builder.py` | 构建 NetworkX 拓扑图：语义边 + 结构边 |
| 4 | WaveSearcher | `src/tagmemorag/wave_searcher.py` | 波扩散检索核心算法（`aggregate: max \| sum`，锚点 `propagation_boost`） |
| 5 | AnchorSystem | `src/tagmemorag/anchor.py` | 锚点 CRUD + 传播增益 + rebuild reconcile（anchor_key 精确匹配 + embedding 最近邻回退） |
| 6 | AppState | `src/tagmemorag/state.py` | 单例持有 `current_graph / stores / anchors / build_id` 原子引用；rebuild 原子 swap；并发 rebuild 锁 |
| 7 | API | `src/tagmemorag/api.py` | FastAPI：`POST /search`, 锚点管理, `GET /graph_info`, `POST /rebuild`（异步）, `GET /rebuild/{task_id}` |
| 8 | CLI | `src/tagmemorag/cli.py` | `build` / `search` / `serve` 命令 |
| 9 | Config | `src/tagmemorag/config.py` | YAML 配置加载（模型、图、检索参数），环境变量 override 留到 M1 |
| 10 | storage.base | `src/tagmemorag/storage/base.py` | 抽象接口：`GraphStore` / `VectorStore` / `AnchorStore`（含增量更新方法签名） |
| 11 | storage.json_graph | `src/tagmemorag/storage/json_graph.py` | `JsonGraphStore` MVP 实现（原子写） |
| 12 | storage.npz_vector | `src/tagmemorag/storage/npz_vector.py` | `NpzVectorStore` MVP 实现（numpy 索引搜索） |
| 13 | storage.json_anchor | `src/tagmemorag/storage/json_anchor.py` | `JsonAnchorStore` MVP 实现 + reconcile 逻辑 |

### 数据流

```
说明书 MD/TXT → Parser → Chunk[] → Embedder → 向量
                                            ↓
                                    GraphBuilder → Graph + Stores 持久化
                                            ↓
用户查询 → Embedder → query_vec → WaveSearcher ← Graph (NetworkX) ← StoreLayer
                                            ↓
                                    Top-K Chunk[] → API Response
```

### 依赖

- `sentence-transformers` (BGE 模型加载)
- `networkx` (拓扑图)
- `numpy` (向量计算)
- `fastapi` + `uvicorn` (REST API)
- `pyyaml` (配置文件)
- `pytest` (测试)

### 预留给后续里程碑的接口钩子

这些**在 M0 不实现**，但 API 签名和代码结构必须就位，避免后续改核心：

- `storage.base` 的 `add_nodes / remove_nodes / delete / update` 方法签名（抛 `NotImplementedError`）— 为增量更新预留
- `VectorStore.search(query, k)` 抽象 — 为 Faiss/Qdrant 预留
- `AppState` 单例封装 graph/stores/anchors + `build_id` — M0 已用（单机 double-buffer），M2 升级"跨进程共享存储 + leader election"
- `api.py` 的 `kb_name` 参数默认 `"default"`（目录为 `data/default/`）— 为 M2 多 KB 预留
- `search_with_metrics(query, trace_id, build_id)` 内部钩子 — 为 M1 日志 / M4 metric 预留
- 错误响应统一格式 `{code, message, detail}` — 为 M3 错误码枚举预留

## Acceptance Criteria (M0)

功能：

* [x] `parse_document(md_path)` 正确按标题切分，超长块(>500字)分割，短块(<50字)合并
* [x] `build_graph(chunks)` 构建的图：语义边(cos>0.5) + 结构边(父子+0.2/兄弟+0.1/连续+0.15)
* [x] `wave_search(query, graph)` 模糊输入能召回正确章节，跨章节检索有效
* [x] 聚合方式默认 `max`，可通过 `config.yaml` 或 `POST /search` 的 `aggregate` 字段切到 `sum`
* [x] 锚点默认只在波源阶段 boost；`propagation_boost > 1.0` 时传播中也放大
* [x] 锚点使用 `anchor_key` 标识；rebuild 后已设锚点通过精确匹配或 embedding 近邻自动重绑，失败者进入 `unresolved_anchors` 返回
* [x] `POST /search` 返回 top-K 结果，每个含 score/text/header/path/node_id
* [x] `POST /anchor` / `DELETE /anchor` / `GET /anchor` 正常工作（以 `anchor_key` 为主键）
* [x] CLI：`python -m tagmemorag build --docs docs/` 和 `--search "xxx"` 可运行
* [x] `POST /rebuild` 异步返回 `{task_id, status}`；`GET /rebuild/{task_id}` 可查状态
* [x] rebuild 期间 `/search` 持续可服（用旧图），无 503，无延迟尖峰 > 100ms
* [x] rebuild 失败时保留旧图，返回 `{code: "REBUILD_FAILED"}`，服务不中断
* [x] 并发 rebuild：第二个请求立即返回 `{code: "REBUILD_IN_PROGRESS"}`
* [x] 每次检索结果包含 `build_id`，便于事后复盘

存储 & 架构预留：

* [x] 存储分层：`GraphStore` / `VectorStore` / `AnchorStore` 抽象接口就位，MVP 用 JSON+NPZ 实现
* [x] 持久化走 `write-to-tmp + os.replace` 原子替换
* [x] `data/{kb}/meta.json` 包含 `schema_version / model_name / model_dim / built_at / chunk_count`
* [x] save → load round-trip：重载后的图对同一查询返回 bit-identical 的 top-K 分数
* [x] 增量接口 `add_nodes / remove_nodes / delete / update` 签名存在，MVP 抛 `NotImplementedError`
* [x] `kb_name` 路径参数存在（默认 `default`），多 KB 目录结构就位
* [x] 错误响应统一格式 `{code, message, detail}`

性能：

* [x] 1000 节点图：构建 < 3s，单次检索 < 20ms（CPU）
* [x] 端到端测试通过："蒸汽很小" → 蒸汽功能 + 故障E05 + 清洗说明

## Definition of Done (M0)

* 单元测试覆盖 6 个核心模块（parser, embedder, graph_builder, wave_searcher, anchor, api）+ 3 个 store 实现
* 端到端测试：用设计文档中的测试用例验证（合成咖啡机说明书 fixture）
* API 可通过 `uvicorn tagmemorag.api:app` 启动并 curl 测试
* CLI 可通过 `python -m tagmemorag` 使用
* `pyproject.toml` 依赖完整，`pip install -e .` 可运行
* save → load round-trip 测试覆盖 JsonGraphStore / NpzVectorStore / JsonAnchorStore

## Out of Scope (M0 — 归属后续里程碑)

**M1 运维基础**：Dockerfile / docker-compose / JSON 日志 / `/health`,`/ready` / 优雅关闭 / 环境变量 override / 模型 warm-up
**M2 零停机 + 多KB**：API key / 限流 / 多副本 rebuild 协调器 / 查询缓存 / 多 KB 真正隔离测试（M0 已覆盖单机零停机）
**M3 质量回归**：Eval 标注集 / precision@k/recall@k/MRR / CI 门禁 / 错误码枚举细化
**M4 观测增强**：Prometheus `/metrics` / OTel traces / 结构化审计日志
**post-v1**：HA 多副本 / Faiss/Qdrant / SSO / 分布式追踪 / Web UI / PDF / 多模态 / 会话上下文 / 反馈学习 / VCPToolBox 时间桶等

## Technical Notes

* 设计文档路径：`/Users/timmy/PycharmProjects/TagMemoRAG/浪潮RAG_产品说明书_详细设计说明书.md`
* VCPToolBox 原始浪潮算法：`/Users/timmy/PycharmProjects/VCPToolBox/Plugin/AgentDream/DreamWaveEngine.js`
* VCPToolBox 已有完整索引，可通过 codebase-memory-mcp 查询
* 目标部署环境：CPU only，4GB 内存，Python 3.11+
* 项目结构：`src/tagmemorag/` 下组织模块
