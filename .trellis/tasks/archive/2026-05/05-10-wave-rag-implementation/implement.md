# implement.md — M0 实施 checklist

> 父文档：[prd.md](./prd.md) / [design.md](./design.md)
> 原则：自底向上实施，每一阶段都跑验证。顺序可按阶段串行。

---

## Phase A — 项目骨架与依赖（~0.5 天）

- [ ] **A1** 更新 `pyproject.toml` 依赖
  - `sentence-transformers>=2.7`
  - `networkx>=3.2`
  - `numpy>=1.26`
  - `fastapi>=0.110`
  - `uvicorn[standard]>=0.27`
  - `pyyaml>=6.0`
  - `pydantic>=2.6`
  - `[dev]`: `pytest>=8`, `pytest-asyncio>=0.23`, `httpx>=0.27`
- [ ] **A2** 创建目录骨架
  ```
  src/tagmemorag/
  ├── __init__.py
  ├── types.py            # Chunk, Anchor, GraphState, Result
  ├── config.py
  ├── parser.py
  ├── embedder.py
  ├── graph_builder.py
  ├── wave_searcher.py
  ├── anchor.py
  ├── state.py            # AppState
  ├── api.py
  ├── cli.py
  ├── errors.py           # 错误码 enum + 异常类
  └── storage/
      ├── __init__.py
      ├── base.py
      ├── json_graph.py
      ├── npz_vector.py
      ├── json_anchor.py
      └── atomic.py       # atomic_write util
  tests/
  ├── fixtures/
  │   └── coffee_machine.md    # 合成说明书用于 E2E
  ├── unit/
  └── e2e/
  config.yaml             # 默认配置
  data/default/           # 运行时生成，.gitignore
  ```
- [ ] **A3** `pip install -e ".[dev]"` 成功

**验证**：`python -c "import tagmemorag"` 不报错；`pytest --collect-only` 能识别 tests 目录。

---

## Phase B — 纯函数核心（~2 天）

不依赖 AppState / 存储，只要能独立单测。

- [ ] **B1** `types.py`：`Chunk` / `Anchor` / `Result` / `GraphState` dataclass；`compute_anchor_key(path, header, text)` 工具函数
- [ ] **B2** `errors.py`：`ErrorCode` enum + `ServiceError(code, message, detail)` 异常；`KbNotLoadedError` 等子类
- [ ] **B3** `config.py`：Pydantic `Settings` 模型映射 `config.yaml` 的每一段；`load_config(path)` 函数
- [ ] **B4** `parser.py`：`parse_document(path) -> list[Chunk]`
  - 测试：空文件 / 无标题 / 多级标题 / 超长块分割 / 短块合并 / 跨层级跳跃
- [ ] **B5** `embedder.py`：`Embedder(model_name, device, batch_size)` 类
  - `encode_batch(list[str]) -> np.ndarray[N, 384]`
  - `encode_query(str) -> np.ndarray[384]`
  - 测试：输出 shape 正确；归一化（`|v|=1`）；同一输入两次结果一致
- [ ] **B6** `graph_builder.py`：`build_graph(chunks, embeddings, cfg) -> nx.Graph`
  - 测试：
    - 两个强相似节点有语义边
    - 父子路径边权 > 裸语义边权
    - 连续块边存在
    - 重复奖励不超过 1.0
- [ ] **B7** `wave_searcher.py`：`wave_search(query_vec, graph, vectors, anchors, **params) -> list[Result]`
  - 测试：
    - 单节点图 → 返回该节点
    - 锚点 boost 生效
    - `aggregate="max"` vs `"sum"` 结果不同
    - `propagation_boost=2.0` 时锚点邻居分数 > 默认时

**验证**：`pytest tests/unit/test_{parser,embedder,graph_builder,wave_searcher}.py` 全绿。

---

## Phase C — 存储层（~1.5 天）

- [ ] **C1** `storage/atomic.py`：`atomic_write(path, write_fn)`；测试断电模拟（写 tmp 后抛异常，原文件不动）
- [ ] **C2** `storage/base.py`：三个 ABC + 增量方法签名（抛 `NotImplementedError`）
- [ ] **C3** `storage/json_graph.py`：`JsonGraphStore.save/load`；NetworkX ↔ JSON 互转
  - 测试：save → load 后图结构严格相等（nodes、edges、attrs）
- [ ] **C4** `storage/npz_vector.py`：`NpzVectorStore.save/load/search`
  - 测试：save → load 矩阵 bit-identical；`search(q, k)` 返回 top-k 与暴力点积一致
- [ ] **C5** `storage/json_anchor.py`：`JsonAnchorStore.save/load/reconcile`
  - 测试：
    - save → load round-trip
    - reconcile：精确命中路径
    - reconcile：小幅文档修改走 embedding 回退成功
    - reconcile：大幅修改进 unresolved
- [ ] **C6** **round-trip 综合测试**：构图 → save 三份 → load → 同一 query 分数 bit-identical

**验证**：`pytest tests/unit/test_storage_*.py tests/unit/test_roundtrip.py` 全绿。

---

## Phase D — AppState 与 Rebuild 并发（~1.5 天）

- [ ] **D1** `state.py`：`AppState` 类（`current / swap / rebuild_lock / rebuild_tasks`）
- [ ] **D2** `anchor.py`：`AnchorSystem` 封装 CRUD（操作 AnchorStore + 更新内存 dict）
- [ ] **D3** 实现 `build_kb(docs_dir, kb_name, cfg) -> GraphState`（纯函数，Parser→Embedder→GraphBuilder→Reconcile→返回新 GraphState 但不 swap）
- [ ] **D4** 实现 `load_kb(kb_name, cfg) -> GraphState`（从 storage 重建）
- [ ] **D5** 实现 `run_rebuild_async(app, docs_dir, kb_name, cfg)`：后台线程调用 `build_kb` → 持久化 → `app.swap(new_state)` → 更新 `rebuild_tasks`
- [ ] **D6** 并发测试：
  - 启动 rebuild 线程（sleep 2s 模拟构建）
  - 同时发 20 个 search → 全部用旧 GraphState 完成，无 error
  - rebuild 完成后 search 用新 GraphState
- [ ] **D7** 失败测试：worker 抛异常 → `_current` 不变 → `rebuild_tasks[id].status = "failed"`
- [ ] **D8** 并发 rebuild：两次 rebuild 同时发，第二次立即 `REBUILD_IN_PROGRESS`

**验证**：`pytest tests/unit/test_state.py tests/unit/test_rebuild_concurrency.py`。

---

## Phase E — API 层（~1.5 天）

- [ ] **E1** `api.py`：FastAPI app + `lifespan` 启动时 `load_kb("default")`
- [ ] **E2** Pydantic 请求/响应模型（与 design §7 契约对齐）
- [ ] **E3** 实现所有端点：
  - `POST /search`
  - `POST /rebuild`（异步 202）
  - `GET /rebuild/{task_id}`
  - `POST /anchor` / `DELETE /anchor/{key}` / `GET /anchor`
  - `GET /graph_info`
- [ ] **E4** 全局异常 handler 把 `ServiceError` 转成 `{code, message, detail}`
- [ ] **E5** `httpx.AsyncClient` 集成测试：
  - 正常 search 路径
  - rebuild 202 → poll status → done
  - 并发 rebuild 拒绝
  - 锚点 CRUD round-trip
  - 错误格式检查

**验证**：`pytest tests/unit/test_api.py`。

---

## Phase F — CLI（~0.5 天）

- [ ] **F1** `cli.py`：基于 `argparse`（不引入 click/typer，减依赖）
  - `python -m tagmemorag build --docs docs/ --kb default --config config.yaml`
  - `python -m tagmemorag search "蒸汽很小" --kb default --top-k 5`
  - `python -m tagmemorag serve --host 0.0.0.0 --port 8000`
- [ ] **F2** `__main__.py` 转发到 `cli:main`

**验证**：手动跑三条命令；`pytest tests/unit/test_cli.py`（子进程调用）。

---

## Phase G — E2E 与 Fixture（~1 天）

- [ ] **G1** 编写 `tests/fixtures/coffee_machine.md`：合成咖啡机说明书，覆盖
  - 章节：产品介绍 / 安装 / 操作（含蒸汽功能） / 维护与清洁 / 故障代码（含 E01/E05）
  - 约 150-200 行，30-50 个块
- [ ] **G2** E2E 测试脚本 `tests/e2e/test_coffee.py`：
  - build KB from fixture
  - 查询 "蒸汽很小" → top-5 必须包含 "蒸汽功能" / "E05" / "清洗"
  - 查询 "不出咖啡" → 包含 "制作咖啡" / "E01"
  - 设置锚点 "紧急停机" → 相关查询分数显著提升
- [ ] **G3** 性能基准：`tests/e2e/test_perf.py`
  - 构建 1000 节点图 < 3s
  - 100 次搜索平均 < 20ms

**验证**：`pytest tests/e2e/ -v`，全部通过。

---

## Phase H — 收尾（~0.5 天）

- [ ] **H1** `README.md` 更新：安装 / build / search / serve 快速开始
- [ ] **H2** `.gitignore`：`data/`、`*.egg-info`、`__pycache__`、`.pytest_cache`
- [ ] **H3** 默认 `config.yaml` 提交
- [ ] **H4** `tests/conftest.py`：通用 fixture（临时 data 目录、默认 config）
- [ ] **H5** 跑一次完整回归：`pytest -v` 全绿
- [ ] **H6** 手动 smoke：`python -m tagmemorag serve` → curl `/search` 看实际输出

---

## 验证命令清单

开发过程中常用：

```bash
# 单元测试
pytest tests/unit/ -v

# E2E
pytest tests/e2e/ -v

# 全部
pytest -v

# 覆盖率（可选）
pytest --cov=tagmemorag --cov-report=term-missing

# 手动启动
python -m tagmemorag serve
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"question": "蒸汽很小", "top_k": 5}'
```

---

## Review Gates（人审时机）

- **Gate 1（Phase B 完成后）**：波算法行为是否符合预期？跑一次 toy 图，肉眼看 top-K 合理。
- **Gate 2（Phase D 完成后）**：rebuild 并发模型是否正确？压力测试报告：N 次 search 无错，延迟 p99。
- **Gate 3（Phase G 完成后）**：E2E 结果是否达到 acceptance criteria 的"蒸汽很小 → 蒸汽+E05+清洗"标准？
- **Gate 4（Phase H 完成后）**：代码总览 + 覆盖率；决定是否 `task.py finish`。

---

## Rollback 点

- Phase C 失败：存储层换回 pickle 临时方案，接口预留
- Phase D 失败：rebuild 改同步阻塞（读写锁方案），降级 NFR 里的零停机承诺
- Phase E 失败：先只暴露 `/search` 和 `/rebuild`，锚点管理走 CLI 后补

回滚都不影响已完成阶段的代码。

---

## 估时总览

| Phase | 估时 | 累计 |
|-------|------|------|
| A 骨架 | 0.5d | 0.5d |
| B 纯函数 | 2d | 2.5d |
| C 存储 | 1.5d | 4d |
| D AppState | 1.5d | 5.5d |
| E API | 1.5d | 7d |
| F CLI | 0.5d | 7.5d |
| G E2E | 1d | 8.5d |
| H 收尾 | 0.5d | 9d |

**M0 总计约 9 人日**。顺序基本串行；B 内部可拆给并行（parser/embedder/graph_builder/wave_searcher 相互独立）。

---

## Out of Scope（再次强调）

本 implement.md 不覆盖 Docker / JSON 日志 / Prometheus / API key / 限流 / Eval / HA / 增量更新实现。这些在 M1-M4 各自的 task 里写。
