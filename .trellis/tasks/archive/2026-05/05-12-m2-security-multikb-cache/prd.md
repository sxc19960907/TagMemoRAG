# brainstorm: M2 安全 + 多KB + 缓存（API key / 限流 / 多知识库 / 查询缓存）

## Goal

在 M1 基础上补齐**生产 API 的安全与承载能力**：入站 API key 鉴权、基础限流、多知识库隔离、查询缓存。完成后 TagMemoRAG 能面对多个客服业务线同时使用，支持按调用方统计/限流，高频问题走缓存不打模型。

## Background / Known Context

### M0+M1 已交付
- FastAPI 端点：`/search / /rebuild / /health / /ready / /anchor` CRUD / `/graph_info`
- `kb_name` **字段**在 API/CLI 里已预留，但当前只接受 `"default"`，其他值返回 404
- `AppState` 只缓存一个 `current: GraphState`，切 kb_name 要重 load
- structlog 日志带 `trace_id`，为 M2 审计打基础
- `POST /search` 每次都 `embedder.encode_query(question)` 走一次模型（本地或 HTTP embedder）
- 错误统一 `{code, message, detail}`，错误码枚举 9 个
- Docker 镜像跑 non-root，`/app/data` 作为 KB 持久化卷

### M2 在路线图的定义（M0 PRD §Milestones）
> **M2 零停机 + 多KB** | API key + 限流 / 多副本 rebuild 协调器 / 多 KB 目录隔离（`data/{kb}/`）/ 查询缓存

### 本 M2 实际范围确认
- **API key + 限流 + 多 KB 隔离 + 查询缓存** — 核心四件套
- **多副本 rebuild 协调器（leader election）** — 延后到 post-v1（当前仍是单节点 HA 需求不紧迫）
- **跨 Pod 限流/缓存一致性** — 延后到 post-v1（M2 使用进程内 store，只保证单进程多线程一致）
- **M4 的 Prometheus metrics** 不包含（限流/缓存会留钩子打日志，M4 再接监控）

## Assumptions (temporary)

- 仍是**单节点部署**（K8s 单 Pod / docker-compose 单实例）
- API 调用方数量 <20（客服/运营系统），key 不需要 DB 存储
- 查询 QPS <50（M2 NFR 目标）
- 缓存容量 <1 万 entry（客服高频问题集中度高，LRU 够用）
- 多 KB 数量 <50（每个产品线一个）
- 限流维度：per API key 而非 per IP

## Decision (ADR-lite)

### Decision: API key 存储 = 配置存 hash，接口化为 DB 迁移留路

**Context**：M2 需要入站 API 鉴权。候选：配置明文 / 配置 hash / SQLite / 外部密钥管理。目标：生产可用 + 简单 + 未来能平滑升级到 DB 动态管理。

**Decision**：
- M2 实现：`ConfigAuthStore` — 从 `config.yaml` 加载 `sha256(secret)` 哈希 + 元数据
- 抽象层：`AuthStore` ABC（`verify(plaintext) -> ApiKey | None`, `list_keys()`, 以及 `touch_usage(key_id)` 等接口）
- 数据契约：`ApiKey` dataclass（`id / label / kb_allowlist / rate_limit_per_minute / scopes / created_at / revoked`）统一用
- 明文 key 格式：`tmr_live_<32 位随机>`（`tmr_test_<...>` 开发用）
- 服务端**永不**存明文；`AuthStore.verify` 用 `hmac.compare_digest` 做常数时间比较

**Rationale**：
- 明文 key 只存在于客户端，服务端即使被逆向也拿不到
- 无新依赖（stdlib `hashlib / hmac / secrets`）
- `AuthStore` 抽象 = 未来 `SqliteAuthStore` / `VaultAuthStore` 直接换实现，API 和调用方零改动
- `ApiKey` dataclass 跨存储后端复用
- `AuthStore.list_keys()` 契约先就位；M2 不暴露 API key 管理端点，post-v1 再开放只读/写入管理 API

**Consequences**：
- `config.yaml` 加 `auth:` 段（开关 + keys 数组）
- 新增模块：`src/tagmemorag/auth/base.py`（接口），`src/tagmemorag/auth/config_store.py`（M2 实现）
- 启动时载入 keys 到内存；M2 的 config 修改需要**重启**生效，post-v1 再加 `SIGHUP`/热 reload
- 日志里统一使用 `api_key_id`，明文 secret 绝不入日志
- `auth.enabled: false` 可关闭鉴权（开发/CI 友好）

**为 DB 迁移预留的钩子**：
- `AuthStore` 接口就位
- `ApiKey` dataclass 带 `last_used_at / created_at / revoked` 字段（配置版内存模拟，DB 版持久化）
- `auth.backend: config | sqlite`（M2 只接受 `config`，DB 版 post-v1 再加）
- API key 管理端点延后到 post-v1；M2 只保留 `AuthStore` 抽象和 CLI 生成工具

### Decision: API key 鉴权方式 = `Authorization: Bearer <key>`

**Context**：M2 决定鉴权 header 的传递方式，影响客户端集成和日志安全。

**Decision**：
- 统一用 **`Authorization: Bearer <key>`**（RFC 6750）
- FastAPI 用 `fastapi.security.HTTPBearer` 依赖
- 豁免路径：`/health / /ready / /docs / /openapi.json / /redoc`，通过 `auth.public_paths` 配置可扩展
- 开发模式：`auth.enabled: false` 时跳过鉴权，日志 `api_key_id=anonymous`
- 错误码映射：
  - 缺失/格式错/无效/已 revoked 的 key → **401 `UNAUTHORIZED`**（不暴露具体原因）
  - 有效 key 但无权访问指定 kb → **403 `FORBIDDEN`**
- **脱敏规则**：日志/响应/错误 detail 中永远用 `api_key_id`（运维定义的稳定 label）；若需展示明文片段用 `tmr_live_abcd****wxyz`（首尾各 4）

**Rationale**：
- 业界标准，客服系统集成零摩擦
- 配合 OpenAPI `securitySchemes` 自动生成，SDK 生成友好
- 和未来 OAuth / JWT 兼容（同一 header 槽位）
- 默认不落反向代理的 access log（比 URL 参数安全得多）

**Consequences**：
- 新增错误码：`UNAUTHORIZED`, `FORBIDDEN`
- `api.py` 加 `Depends(verify_api_key)` 到所有需要保护的端点；豁免路径走另一条链
- structlog 中间件在 trace_id 旁再 bind 一个 `api_key_id`（开发模式下 `anonymous`）
- OpenAPI doc 会自动出现 🔒 标识

### Decision: 限流 = 滑动窗口计数 + 内存 dict（RateLimitStore 抽象）

**Context**：M2 需要 per-key 限流，单节点部署。候选：固定窗口/滑动日志/滑动计数/令牌桶；内存/Redis。

**Decision**：
- **算法**：滑动窗口计数（业界主流，内存 O(1) + 近似精确，误差 <5%）
- **存储**：进程内内存 dict，`RateLimitStore` ABC 抽象（为 post-v1 Redis 迁移留路）
- **粒度**：per `api_key_id`（不是 per IP）
- **时间函数可注入**：`now_fn=time.time` 默认，测试用 mock 推进时间
- **全局兜底**：`auth.global_max_rate_limit_per_minute` 作为 key 级配额的上限
- 超限响应：`HTTP 429 + {"code": "RATE_LIMITED", "detail": {...}}`，header 带 `Retry-After / X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset`
- 正常响应也带 `X-RateLimit-*` 头，客户端可自适应
- 豁免：`/health / /ready` 永不限流；豁免路径清单与鉴权共用

**Rationale**：
- 滑动窗口计数是 Cloudflare/Kong/Stripe/OpenAI 等公开使用的算法；比固定窗口无边界尖峰，比滑动日志省内存
- 令牌桶的 burst 语义对"每分钟 N 次"配额过度设计
- 单节点不需要 Redis；跨进程一致性不存在
- `RateLimitStore` 抽象 = post-v1 HA 时直接替换为 `RedisSlidingWindowStore`（~50 行），算法代码零改动

**Consequences**：
- 新增模块：`src/tagmemorag/rate_limit/base.py`（ABC），`src/tagmemorag/rate_limit/memory_sliding.py`
- 新增错误码：`RATE_LIMITED`（HTTP 429）
- `api.py` 中间件链增加限流依赖（鉴权之后，缓存之前）
- 日志事件 `rate_limited`（仅超限时打，允许的不打，避免 log flood）
- 限流数据进程重启丢失 — M2 可接受（客户端 Retry-After 自然恢复）

### Decision: 多 KB 权限模型 = kb 白名单 + scopes 字段（M2 最小集）

**Context**：M2 开启真正的多 KB 隔离，每个 key 应该只能看到自己的产品线 KB。

**Decision**：
- 每个 `ApiKey` 带 `kb_allowlist: list[str]` 字段
  - `[]`（空列表）或 `["*"]` = 全允许（admin / superuser）
  - 具体 kb 名列表 = 仅允许列出的 KB
- 每个 `ApiKey` 带 `scopes: list[str]` 字段（M2 最小集）
  - `search` → `/search`, `/graph_info`, `GET /anchor`, `GET /kb`
  - `rebuild` → `POST /rebuild`, `GET /rebuild/{task_id}`
  - `anchor.write` → `POST /anchor`, `DELETE /anchor/{key}`
  - `admin` → 所有端点 + **无 kb_allowlist 约束**（即使 allowlist 非空，admin 也全通）
- 中间件链顺序：**authenticate → authorize (scope + kb) → rate_limit → cache → handler**
- `GET /kb` 只列出当前 key 有权访问的 KB（防枚举）
- 错误映射：
  - scope 不够 → **403 `FORBIDDEN`** + detail `{"required_scope": "rebuild"}`
  - kb_name 不在白名单 → **403 `FORBIDDEN`** + detail `{"kb_name": "...", "allowed": [...]}`

**Rationale**：
- 白名单模型对"多产品线隔离"是最清晰的表达
- scopes 字段 M2 实现 4 个最小 scope，post-v1 扩展（比如 `config.read` / `metrics.read`）不改契约
- 显式配置易审计：运维 grep `kb_allowlist` 能看到"谁能访问什么"
- 避免标签 ACL 的过度工程

**Consequences**：
- `ApiKey` dataclass 包含 `kb_allowlist / scopes`
- 新增依赖函数 `verify_scope(required: str)` 和 `verify_kb_access(kb_name: str)` — FastAPI `Depends` 组合
- 新增 `/kb` 端点（列表），受 `search` scope 保护
- `POST /rebuild` 改为受 `rebuild` scope 保护
- `/anchor` CRUD：读走 `search`，写走 `anchor.write`
- 端到端测试：同一 key 访问允许 KB 通过、访问禁止 KB 返回 403、admin key 跨 KB 通过

### Decision: 查询缓存 key = query + kb + build_id + 所有参数 + anchors_version

**Context**：M2 引入查询缓存，cache key 组成直接决定正确性和命中率。

**Decision**：
- cache key 的输入：`kb_name / build_id / anchors_version / question(normalized) / top_k / source_k / steps / decay / amplitude_cutoff / aggregate`
- 实现：`sha256("\0".join(map(str, inputs)))`（`\0` 作分隔符防歧义拼接）
- **question 归一化**：`" ".join(q.strip().split())`（压缩内部空白，保留大小写）
- **anchors_version**：`GraphState.anchors_version: int`，每次 anchor add/delete 递增；load_kb 时从 anchors.json 恢复
- **build_id** 变化自动失效（rebuild 完成后整个 KB 的旧缓存自然 miss，LRU 淘汰）
- TTL：默认 3600s（防止长期驻留的"幽灵结果"）
- LRU 容量：默认 10000 entry（全局共享，不按 KB 分桶）
- 响应字段新增 `cache: "hit" | "miss"`；命中返回新的 `trace_id` 和新的 `search_time_ms`（命中本身耗时）
- 日志事件 `search` 加 `cache=hit/miss`

**配置**：
```yaml
cache:
  enabled: true
  max_entries: 10000
  ttl_seconds: 3600
```

**Rationale**：
- 任何影响结果的输入都进 key → 正确性 100% 保证
- `build_id` 和 `anchors_version` 天然解决失效问题，**不需要主动清理**
- question 归一化捕获日常输入噪音（多一个空格/前后空白）
- LRU 全局共享：热门 KB 自然占更多 entry，冷门 KB 不浪费

**Consequences**：
- 新增模块：`src/tagmemorag/cache/base.py`（`QueryCache` ABC），`src/tagmemorag/cache/lru_ttl.py`
- `GraphState` 新增 `anchors_version: int = 0`；`anchors.json` schema 加 `version` 字段
- `AnchorSystem.add / delete` 调用后 `state.anchors_version += 1`
- `api.py` 中间件链：鉴权 → 限流 → **缓存检查** → handler
- 缓存命中时**不走 embedder**，大幅降低高频问题成本
- 测试：
  - 同一 query 二次请求 → hit
  - 换 kb_name / top_k / aggregate → miss
  - rebuild 后原 query → miss
  - 锚点变更后 → miss
  - LRU 溢出淘汰最旧

### Decision: rebuild 对缓存 = 被动自然淘汰 + admin 手动清理端点

**Context**：cache key 已经包含 build_id，rebuild 后老 entry 自然失效。问题退化为"是否主动清理"。

**Decision**：
- **被动自然淘汰**：rebuild 完成后不做任何主动清理，老 build_id 的 entry 变"死 entry"，LRU 自然挤出去
- **admin 端点**：`POST /admin/cache/clear`（受 `admin` scope 保护）
  - body 可选 `{"kb_name": "xxx"}`；缺省清所有
  - 日志事件 `cache_cleared` 含 `cleared_count / kb_name`
- `QueryCache` 接口保持最小（`get / set / clear / clear_by_kb`），不强制加 `invalidate_by_build_id` 等方法
- cache eviction 不受 shutdown 阻塞（内存数据随进程退出释放）

**Rationale**：
- 10k LRU × 50 KB = 50 万 entry 的最坏情况下，热查询流量几分钟就把死 entry 挤空；短暂占内存可接受
- 主动清理给接口加方法，post-v1 接 Redis 时分布式清理麻烦；被动淘汰策略跨后端一致
- admin 手动清理端点覆盖"缓存怀疑污染"的运维场景
- `cache_evicted` 事件不打（LRU 频繁淘汰会 log 爆炸）

**Consequences**：
- `QueryCache.clear(kb_name: str | None = None)` 作为唯一人工介入点
- `/admin/cache/clear` 端点需要 `admin` scope
- 新增日志事件 `cache_cleared`

## Open Questions (blocking / preference)

1. ~~API key 存储方式~~ → **config 存 sha256 hash + AuthStore 抽象（为 DB 留路）** (decided)
2. ~~API key 鉴权方式~~ → **`Authorization: Bearer <key>` + HTTPBearer + public_paths 豁免** (decided)
3. ~~限流算法与存储~~ → **滑动窗口计数 + 内存 dict + RateLimitStore 抽象** (decided)
4. ~~多 KB 权限模型~~ → **kb 白名单 + scopes 字段（search / rebuild / anchor.write / admin）** (decided)
5. ~~查询缓存 key 组成~~ → **kb + build_id + anchors_version + 归一化 question + 所有参数** (decided)
6. ~~rebuild 对缓存的影响~~ → **被动自然淘汰 + `/admin/cache/clear` 手动端点** (decided)

所有 M2 核心决策已锁定，进入 design.md / implement.md 撰写。

## Requirements (草稿，brainstorm 期间细化)

### 1. API key 鉴权
- 运维能配置多个 key + 每个 key 的元数据（label / kb_allowlist / rate_limit）
- 请求没带 key 或 key 无效 → 401
- 日志记录 `api_key_id`（脱敏）而非 key 本身
- key 轮换通过修改 `config.yaml` 后重启生效；热 reload 延后到 post-v1

### 2. 限流
- 每个 key 独立配额（如 100 req/min）
- 超限返回 429 + `Retry-After` 头
- 默认配额可全局配置

### 3. 多 KB 隔离
- `data/{kb_name}/` 目录结构已就位（M0 预留），M2 真正支持多 KB 并存
- `AppState` 升级为**多 KB 容器**（从单 `current` → `dict[kb_name, GraphState]`）
- 每个 KB 独立的 double-buffer rebuild 状态
- API 参数 `kb_name` 路由到对应的 KB
- `GET /kb` 列出当前 API key 有权访问的 KB + 状态（admin 可见全部）

### 4. 查询缓存
- LRU + TTL 内存缓存
- cache key 包含查询内容 + kb_name + 搜索参数 + build_id（build_id 变化即失效）
- 缓存命中直接返回（不走 embedder），日志标记 `cache=hit`
- `search_time_ms` 区分命中（<1ms）和未命中

## Acceptance Criteria (evolving)

功能：
- [ ] 无 API key 的请求返回 401 `UNAUTHORIZED`
- [ ] 无效 API key 返回 401 `UNAUTHORIZED`
- [ ] 合法 key 能正常调用 `/search`
- [ ] `/health` `/ready` **不**需要 API key（K8s probe 不能带 key）
- [ ] 超过配额返回 429 `RATE_LIMITED` + `Retry-After` 头
- [ ] 同一 key 在单进程多线程/多连接并发下计数一致（跨 Pod 一致性 post-v1 通过 Redis 等外部 store 实现）
- [ ] 两个 KB 并存，查询 A 不影响 B
- [ ] `POST /rebuild` 带 `kb_name=B` 时 A 的查询不受影响
- [ ] 相同查询两次，第二次 `cache=hit` 且 `search_time_ms < 1`
- [ ] rebuild 后对应 KB 的缓存失效（新 build_id）
- [ ] `GET /kb` 按当前 key 的 allowlist 列出可见 KB 及其 build_id / node_count / status（admin 可见全部）

性能：
- [ ] 缓存命中 p95 < 5ms
- [ ] 50 QPS 稳定运行（缓存命中率 >70% 时）

可观测：
- [ ] 每条日志含 `api_key_id / kb_name / cache_status`
- [ ] 限流日志事件 `rate_limited` 含 `api_key_id / limit / window`

## Definition of Done

- 单元测试：key 鉴权（4 种场景）/ 限流（未超/刚超/跨 key）/ 多 KB（隔离/并存 rebuild）/ 缓存（命中/失效/LRU 淘汰）
- 集成测试：docker-compose 下两个 KB 并存端到端
- 文档：README 新增 "认证 / 限流 / 多 KB / 查询缓存" 章节
- 回归：M0+M1 的所有测试保持绿

## Out of Scope (explicit)

- 多副本 rebuild 协调器 / leader election → post-v1（单节点够用）
- Prometheus `/metrics` → M4
- OpenTelemetry traces → M4
- 更细粒度 RBAC（比如按 anchor label、具体端点或操作对象授权） → post-v1；M2 仅实现 `search / rebuild / anchor.write / admin` 四类 scope
- 外部密钥管理（Vault / AWS Secrets Manager 集成） → post-v1
- 分布式缓存（Redis） → post-v1
- Eval 回归 → M3

## Technical Notes

- 新依赖候选：`limits` 或 `slowapi`（限流），`cachetools` 或 stdlib（缓存）
- 影响面：`api.py / state.py / config.py`，新增 `auth.py / rate_limit.py / cache.py / kb_manager.py`
- 向后兼容：`kb_name` 默认 "default"，老客户端零改动
