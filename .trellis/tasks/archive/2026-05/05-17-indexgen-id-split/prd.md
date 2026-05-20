# T1 — IndexGeneration mechanism + ID system split (A1 + A4 from architecture.md)

## Goal

Implement the IndexGeneration mechanism (A4) and the ID system split (A1) defined in `.trellis/spec/backend/architecture.md`. The goal is to make embedder/chunker/parser version upgrades safely reversible: a new generation is built in shadow, validated, swapped atomically, and old generations remain available for rollback until explicitly retired.

This is the foundation task of the architecture-v2 follow-up roadmap (T1). T2 (QueryPlan + SQLite plan log) and T3 (Reranker first-class) depend on it; T6/T7/T8/T9 also depend on it for safe rebuild.

## Background / Known Context

Repo state inspected on 2026-05-17:

- `chunk_id` derivation (`src/tagmemorag/chunk_identity.py`): already does NOT include embedder fields. `parser_signature` contains parser config only. **A1 chunk_id is already clean — no churn needed there.**
- Qdrant point id (`storage/qdrant_vector.py:_point_struct`): currently uses `node_id` (rebuild-local int) as the point id, with `kb_name` and `node_id` in the payload. **This is the lever to flip for A1: replace `node_id` with `vector_point_id = hash(chunk_id, embedding_model_id, embedding_model_version)`.**
- Qdrant collection naming (`storage.qdrant_vector.collection_name`): `{prefix}_{kb}` — must extend to `{prefix}_{kb}_g{N}`.
- File storage: per-KB directory with `graph.json` / `vectors.npz` / `chunk_identity.json` / assets, no generation subdir today.
- `AppState.swap_kb` is a simple reference replacement under a lock; no shadow/active concept.
- `build_kb_incremental` (`src/tagmemorag/incremental_rebuild.py`) is heavy: anchor reconcile, tag retrain, EPA retrain, impact reports. The shadow build path must call this same flow into a different generation directory, not a parallel implementation.

Architecture references:

- A1 (ID split): `architecture.md` § "A1. ID System Split". `chunk_id` stays embedder-free; `vector_point_id = hash(chunk_id, embedding_model_id, embedding_model_version)` replaces `node_id` as the Qdrant point id.
- A4 (IndexGeneration): `architecture.md` § "A4. IndexGeneration". State machine: empty → g1 active → (g1 active, g2 shadow) → g2 active (g1 retired*) → retire. Admin API: build-shadow / swap / retire / status. No traffic split.
- Real-flow comparison via offline replay against shadow (links to C9 + T5), NOT in this task.

## Scope

### Code changes

1. **chunk_id audit (A1.a)**: confirm by test that `chunk_id` derivation contains no embedder coupling; lock with a regression test.
2. **vector_point_id introduction (A1.b)**: derive `vector_point_id = hash(chunk_id, embedding_model_id, embedding_model_version)`; replace `node_id` as the Qdrant point id; payload still carries `node_id` for runtime convenience but is no longer the durable key.
3. **Generation-aware Qdrant collection naming (A4.a)**: `collection_name(prefix, kb, generation)`; existing collections aliased or one-time renamed to `g1`.
4. **Generation-aware file layout (A4.b)**: introduce `{kb_root}/g{N}/...` subdirectory; add `{kb_root}/meta.json` with `active_generation`, `shadow_generation`, `history[]`.
5. **Shadow build (A4.c)**: `build_kb_incremental` (or a wrapper) accepts a target generation id and writes into `g{N}/`; existing flow becomes "build for active or shadow", not "always overwrite".
6. **AppState dual generation (A4.d)**: `AppState` holds `active_state` and optional `shadow_state` per KB; current `kb_swap` semantics preserved for active swaps; new method for swap+retire semantics.
7. **Admin API (A4.e)**: 4 endpoints — `POST /admin/generation/build-shadow`, `POST /admin/generation/swap`, `POST /admin/generation/retire`, `GET /admin/generation/status`. Auth aligned with existing admin endpoints.
8. **Trigger conditions enforcement (A4.f)**: rebuild path checks whether `parser_version` / `chunker_version` / `embedding_model_id` / `embedding_model_version` / `index_schema_version` change implies a new generation; in-place mutation only allowed for content-only changes (new docs in same KB).

### Non-code

9. **Migration**: existing single-collection KBs must continue to work after this change ships. Migration approach (alias/rename `{prefix}_{kb}` → `{prefix}_{kb}_g1`; introduce `meta.json` with `active_generation=1`) decided during design.
10. **Memory + spec updates**: when meaningful invariants surface, update spec or write memory; do not invent constants.

## Decisions (ADR-lite)

### D1 迁移机制：rename + alias（A 方案）

**Context**：现有 KB 走 `{prefix}_{kb}` 单 collection 单目录结构，需要变成 generation-aware。
**Decision**：迁移采用就地改名。
- 文件层：检测到 `{kb_root}/graph.json` 等 legacy 文件存在但 `meta.json` 不存在时，移动到 `{kb_root}/g1/`，写 `meta.json` 标记 `active_generation=1`。`os.rename` 是原子的。
- Qdrant 层：用 `create_alias` 把现有 `{prefix}_{kb}` collection alias 到新名 `{prefix}_{kb}_g1`，业务代码统一通过 `{prefix}_{kb}_g{N}` 命名读写。alias 期间双名都能命中。
- 触发时机：应用启动时 lazy migrate per KB，幂等。
**Consequences**：
- 零数据丢失，零 rebuild。
- Qdrant 旧 collection 保留物理名一段时间作为 alias 后端；不影响功能；retire 流程可在某个 generation 不再被任何 alias 引用时清理。
- 迁移代码必须幂等（startup 多次调用安全）。

### D2 `meta.json` shape：每个 generation 简介 + shadow 进度（B 方案）

**Context**：admin status API 是刚需；shadow 构建进度必须有地方存（构建未完成时 `g{N}/` 内部 meta 还不存在）。
**Decision**：`{kb_root}/meta.json` 是权威索引，结构如下：

```json
{
  "schema_version": 1,
  "active_generation": 2,
  "shadow_generation": 3,
  "generations": {
    "1": {
      "created_at": "ISO-8601",
      "retired_at": "ISO-8601 or null",
      "parser_version": "...",
      "chunker_version": "...",
      "embedding_model_id": "...",
      "embedding_model_version": "...",
      "index_schema_version": int,
      "chunk_count": int
    },
    "2": { "...same fields...", "retired_at": null },
    "3": {
      "status": "building" | "ready" | "failed",
      "progress": float 0-1,
      "build_started_at": "ISO-8601",
      "trigger_diff": ["embedding_model_id", ...]
    }
  }
}
```

**Invariant**：`{kb_root}/meta.json` 是索引（admin status 单点读），`{kb_root}/g{N}/...` 是数据。索引在 swap/retire/build 阶段更新；数据写完后只读。
**Consequences**：
- admin status API 实现简单：读一个文件返回。
- meta.json 写入必须走 `storage/atomic.py:atomic_write`，避免并发写入腐蚀。
- `g{N}/` 内部可以有自己的 detail meta（例如 build manifest），但不能与外层 meta 冲突；冲突时外层为准。

### D3 Build-shadow 撞车策略：拒绝 + 配套 cancel-shadow API（A 方案）

**Context**：shadow build 是慢操作（embedder 全量 KB，可能几分钟到几小时），不应该默默吞掉前面的工作。
**Decision**：
- `POST /admin/generation/build-shadow`：当前已有 shadow 在建（`meta.json.shadow_generation` 不为 null 且 status=building）→ 返回 `409 SHADOW_BUILD_IN_PROGRESS`，body 含当前 shadow id 和 progress。
- 新增 `POST /admin/generation/cancel-shadow`：取消正在构建的 shadow，清掉 `g{N}/` 目录和 `meta.json` 里的 shadow 槽。已经 ready 的 shadow 也允许 cancel（等同于 retire-shadow，不影响 active）。
- 进程崩溃恢复：服务启动时若发现 `meta.json.shadow.status=building` 但没有活跃构建任务，自动标记为 `failed`；操作员需 cancel-shadow 清理后重新发起。
**Consequences**：
- admin API 列表从 4 个增至 5 个：build-shadow / cancel-shadow / swap / retire / status。
- 错误码新增 `SHADOW_BUILD_IN_PROGRESS` / `SHADOW_BUILD_FAILED`。
- 进程内需要一个 in-memory 的 "shadow build 任务句柄" 用于 cancel 和 progress 更新；落地形式（asyncio task / threading.Thread / subprocess）由 design.md 决定。

### D4 Retire 安全窗口：默认 24 小时强制等待 + force override（C 方案）

**Context**：retire 不可逆；新版本上线后需要观察窗口判断是否回滚。同时磁盘紧张或确认无误时需要应急出口。
**Decision**：
- `meta.json` 里 `generations[N].swap_at` 记录 swap 时间。
- `POST /admin/generation/retire`：默认检查 `now - swap_at >= retire_min_hours_after_swap`（默认 24 小时）。未到 → `409 RETIRE_TOO_EARLY`，body 含 `retry_after_seconds`。
- 请求体支持 `force: true`，绕过等待。响应需要操作员级 confirmation（强 confirmation 实现细节由 design.md 决定，至少在 admin UI 加二次确认）。
- `Settings.retire_min_hours_after_swap` 配置项，默认 24，可调。
**Consequences**：
- 错误码新增 `RETIRE_TOO_EARLY`。
- meta.json 字段补充 `swap_at`（每个曾经成为 active 的 generation 都有这个字段）。
- 测试需覆盖：足够时间后 retire 通过；不足时间被拒；force=true 绕过。
- 磁盘与 KB 大小线性相关，24 小时双代共存对当前规模可接受。

### D5 NPZ 后端也支持完整 generation（A 方案）

**Context**：CI 主要跑 NPZ（无 Qdrant 外部依赖）；A4 是关键安全机制必须有完整测试覆盖。
**Decision**：NPZ 与 Qdrant 两种向量后端都完整支持 IndexGeneration。
- NPZ 路径：`{kb_root}/g{N}/vectors.npz`，shadow 构建写新文件，swap 改 `meta.json` 指针。
- Qdrant 路径：`{prefix}_{kb}_g{N}` collection（D1 alias 机制处理迁移）。
- 同一套 admin API、同一套错误码、同一套状态机，无后端差异。
**Consequences**：
- 测试可在 NPZ 后端覆盖完整 IndexGeneration 流程，无需 Qdrant 实例。
- 向量存储抽象层（`storage/base.py` 等）需要新增 generation-aware 方法或参数。
- 未来引入第三种向量后端（如 Milvus）时同一契约可复用。

### D6 衍生品（tag embeddings / EPA basis / tag co-occurrence / tag residuals）按 generation 各算一份（A 方案）

**Context**：所有衍生品本质都依赖 chunk embedder 输出；混代会破坏 A4 "swap 一次性原子" 承诺，且 rollback 语义会变复杂。
**Decision**：所有衍生品和主向量一同放进 `{kb_root}/g{N}/`，shadow build 一次性算齐，swap 把整个 generation 一起切换，retire 一次性清理。
- 涉及衍生品：`tag_embeddings.npz`、`epa_basis.npz`、`tag_cooccurrence.json`、`tag_intrinsic_residuals.npz`、`anchors`、`chunk_identity.json`、`graph.json`、`vectors.npz`（NPZ 后端）。
- shadow build 阶段必须串行调用现有 retrain 流程（`sync_rebuild_tags`、`retrain_report` 等）写入 `g{N}/`。
- retire 删 generation 目录时一并清理。
**Consequences**：
- shadow build 时间略增（衍生品算时间，相对 embedder 全量是小头）。
- 每代磁盘占用 = 主向量 + 衍生品；24 小时双代共存时，总磁盘约 2× 单代；retire 后回到 1×。
- 现有 retrain 函数需要支持 "写到指定 generation 目录" 而非默认 KB 目录；这是普通参数化改动，没有架构改动。
- 回滚语义干净：rollback active=g3 → active=g2 一次性把所有衍生品也回退。

### D7 Swap 后的增量 rebuild：直接写入 active generation（A 方案）

**Context**：内容变更（新文档、文档更新）不应触发新 generation；version 字段不变时增量 rebuild 直接更新 active generation。
**Decision**：
- `g{N}` 是"激活版本的累积状态"，不是"build-shadow 那一刻的不可变快照"。
- 增量 rebuild（content-only change）直接写入当前 active 的 `g{active}/` 目录与对应 Qdrant collection。
- shadow build 启动时，以 KB 当时全部内容（包括 active 的累积增量）为输入构建 g{N+1}。
- retire 时一并清理 generation 内的累积增量。
- 触发条件：`parser_version` / `chunker_version` / `embedding_model_id` / `embedding_model_version` / `index_schema_version` 任一变更才创建 shadow；其它任何变更走增量 rebuild on active。
**Consequences**：
- 现有 `build_kb_incremental` 语义保持，只把目标目录从 KB 根改为 `g{active}/`。
- shadow build 开始时拍一份 active 的最新内容快照作为输入；构建窗口期内 active 上来的新增量仍写 active；shadow swap 后这些"窗口期增量"由下一次 active 上的增量 rebuild 处理（即 swap 后第一次 build_incremental 会发现差异并补齐）。
- 测试需覆盖：active 增量后再 build-shadow，新内容进 shadow；swap 后 active 上又有增量，行为正常。

### D8 build-shadow 版本来源：body 可选指定 + swap 时回写 Settings（C 方案）

**Context**：A 强制重启违背 zero-downtime；B 的 Settings 漂移让 active 真实状态和 Settings 不一致。
**Decision**：
- `POST /admin/generation/build-shadow` body 字段 `embedding_model_id` / `embedding_model_version` / `parser_version` / `chunker_version` / `index_schema_version` 全可选；缺省读当前 `Settings`。
- 至少一个字段必须与当前 active 不同，否则 `400 NO_VERSION_DIFF`（对应 architecture A4 的 trigger 条件）。
- shadow 构建过程中按 body 里的版本动态实例化 embedder / parser / chunker；不修改全局 Settings。
- `POST /admin/generation/swap` 成功后，把新 active 的版本字段**回写 Settings 持久化文件**（用 `storage/atomic.atomic_write`），并刷新进程内 Settings；保证 Settings 与 meta.json 一致。
- 服务启动时检测 `Settings` 与 `meta.json.generations[active]` 版本不一致 → 启动失败并打印明确错误（要求操作员手工对齐）；不静默自纠。
**Consequences**：
- embedder / parser / chunker 工厂需支持按版本字符串动态实例化；现有静态实例化处需要重构为按需构造。
- Settings 退化为"默认值 + 启动时与 meta.json 一致性校验"。
- 需要新增错误码：`NO_VERSION_DIFF`、`SETTINGS_META_MISMATCH`。
- swap 成功的写入顺序：先写 meta.json（atomic）→ 再写 Settings 文件（atomic）→ 再刷新进程内 Settings。中间任一步失败的恢复策略由 design.md 定。

### D9 索引文件名：`index.json`（避免与 GraphState meta 冲突）

**Context (Slice 4 实施时发现)**：现有 `state.save_kb()` 已经在 `{kb_root}/meta.json` 写 GraphState 元数据（schema_version、model_name、build_id、chunk_count、impact_report 等）。原 D2 决议把 IndexGeneration 索引也叫 `meta.json`，两边语义不同会互相覆盖。
**Decision**：IndexGeneration 索引改名为 `{kb_root}/index.json`。GraphState 元数据继续用 `meta.json`，并在迁移时跟随其他 g1 artifacts 一起搬进 `g1/meta.json`（这是它本来的逻辑归宿——它本来就是单 generation 内的元数据）。
**Consequences**：
- D2 文本中的 "meta.json" 实际指 `{kb_root}/index.json`；架构文档（architecture.md）+ 任务设计（design.md）+ 实施清单（implement.md）已同步改名。
- migration 的 LEGACY_FILES 加入 `meta.json`，迁移时一起进 g1。
- PRD 的 D1–D8 历史决议正文保留原文（"meta.json"），所有真实命名以 D9 + 代码常量 `INDEXGEN_META_FILENAME = "index.json"` 为准。

### D10 Shadow build 实现路线：独立 `build_shadow_kb` 函数（Z 方案）

**Context (Slice 5 实施前)**：现有 `build_kb_incremental` 内部硬编码大量 `_kb_dir`/`save_kb`/`save_chunk_identity`/`save_rebuild_impact`/`sync_rebuild_tags` 调用，无法直接注入 `KbPaths` 让产物落到 `g{N+1}/`。三种路线对比：X 全链路传 paths（影响面大易污染 active）、Y monkey-patch Settings.data_dir（破坏 `_global` 共享路径）、Z 独立 shadow build 函数。
**Decision**：新写 `src/tagmemorag/indexgen/shadow_build.py:build_shadow_kb(...)`。
- shadow build 语义本就是**全量从零构建**——用新 embedder 把整个 KB 重新 parse + chunk + embed + build_graph，不需要 `build_kb_incremental` 的 chunk-identity 复用逻辑。
- 复用现有可重入子函数：`parse_document` / `chunk` 流程 / `embedder` / `build_graph` / 产物 retrain（`sync_rebuild_tags`、`retrain_report`、`build_chunk_identity_map` 等）。
- 通过 `KbPaths(kb, cfg, target_gen)` 把所有产物写入 `g{N+1}/`，对 active 完全隔离。
- D6 衍生品要求：tag/EPA/co-occurrence/residuals 都按 generation 写入 `g{N+1}/`；`_global/` 共享路径不在 shadow build 范围内（属于 KB 间共享，由全局 retrain 流程负责）。
**Consequences**：
- `build_kb_incremental` 不动，active 增量 rebuild 路径零回归风险。
- shadow build 不依赖 `chunk_identity.json` 增量复用——每次 shadow 都是全量 embedder 调用（这是 D8 触发条件本身要求的：换 embedder 就要全量重算）。
- shadow build 函数对外契约：`build_shadow_kb(docs_dir, kb, target_versions, paths) -> GraphState`，不涉及 AppState；接进 AppState 由 Slice 5 第二步 `start_shadow_rebuild` 完成。
- 必须解决：`sync_rebuild_tags` 等下游函数当前用 `_kb_dir(kb, cfg)` 写入；shadow build 调用时需要它们尊重 `KbPaths(generation=N+1)`。逐个评估：可改的最小路径用 paths 注入；不可改的（如 `_global` 路径）保持现状（shadow 与 active 共享）。

### D11 D6 范围收紧：T1 内只隔离 graph/vectors/chunk_identity（C 方案）

**Context (Slice 5 实施时发现)**：D6 决议要求衍生品（tag embeddings / EPA basis / co-occurrence / residuals）按 generation 各算一份。但代码现状：这些 artifact 存在 `{data_dir}/_global/...` 而非 `{kb_root}/...`，是**跨 KB 共享**的全局结构（见 `epa_basis.py:54`、`tag_cooccurrence.py:35`）。把它们改成 generation 级会改变底层全局共享语义，工程量超出 T1 范围。
**Decision**：T1 范围内 shadow build 只 generation 级隔离 KB-级 artifact：
- `g{N}/graph.json`
- `g{N}/vectors.npz`（NPZ 后端）/ `{prefix}_{kb}_g{N}` Qdrant collection
- `g{N}/chunk_identity.json`
- `g{N}/anchors.json`
- `g{N}/meta.json`（GraphState 元数据）

跨 KB 共享的全局 artifact（EPA basis / tag co-occurrence / tag intrinsic residuals）**保持全局**，不进 generation 子目录。tag embeddings 当前由 `sync_rebuild_tags` 写到 `_global/`-类共享存储，**T1 内 shadow build 不动它们**——swap 后由 active 路径正常的 retrain 流程负责更新。
**Consequences**：
- 失去"swap 一次性原子带衍生品"承诺。短窗口期间（swap 后到下一次全局 retrain 完成）衍生品仍反映旧 active 的状态，但不会破坏检索（衍生品只影响 wave/tag-co-occurrence 路径，主检索路径不依赖）。
- 这是 T1 工程量的现实妥协——彻底的衍生品 generation 化推到后续 T1.5 任务（路线图增加）。
- shadow build 函数契约简化：只需写 graph/vectors/chunk_identity/anchors/meta 五件。
- 文档：architecture.md A4 需要追加 "T1 scope: only KB-level core artifacts isolated; KB-shared global artifacts deferred"，避免架构文档与 T1 行为不符。

### D12 D8 收紧：Settings 同步只在进程内做（不写 yaml）

**Context (Slice 6 实施前)**：D8 原文要求 swap 成功后把版本字段回写 Settings 持久化文件。但配置文件可能被 git 维护、可能在容器里只读、可能由 ops 工具管理；编程式重写带来真实风险。
**Decision**：swap 完成后只更新进程内 Settings 对象的字段（in-place mutate cfg.model 的 `embedding_model_id`/`embedding_model_version`、cfg.storage 的 `schema_version`），**不**写回 yaml/json 配置文件。
- 真实事实源依然是 `index.json`，启动时从 `index.json` 读 active 版本，不依赖 Settings 文件的字段（Slice 8 启动校验保证两者一致或拒绝启动）。
- 这种"index.json 权威 + Settings 镜像"避免了文件竞争。
- 副作用：Settings 内存值在重启后会从 yaml 重新加载——但 Slice 8 校验会立即 catch 不一致并要求人工处理。
**Consequences**：
- swap 实现简化：只 mutate cfg 对象，不 atomic_write 配置文件。
- D8 中的"swap 成功 → 回写 settings 文件"语义降级为"swap 成功 → mutate 进程内 cfg + 留待 Slice 8 启动校验对齐"。
- T1 实现保持单进程语义；多进程部署下重启后需要 ops 手工对齐 Settings 与 active generation 版本。

## Open Questions

All blocking questions resolved during brainstorm (D1–D8). Remaining detail-level decisions deferred to `design.md` drafting:

- exact error code names and HTTP statuses
- shadow build async runtime choice (asyncio task / threading / subprocess)
- exact recovery flow when swap-write-meta succeeds but Settings-write fails
- whether `meta.json.history[]` is bounded (e.g. last 10 generations) or unbounded
- Q3 Build-shadow concurrency: what happens if `build-shadow` is called while another shadow build is in progress? 409? queue? cancel-and-restart?
- Q4 Retire safety window: is there a hard minimum delay between swap and retire (e.g. ≥1 hour)? Or operator-only discretion?
- Q5 NPZ-backed (no Qdrant) deployments: do they need full generation support too, or is generation an opt-in capability tied to Qdrant?
- Q6 Tag rebuild and EPA retrain: are these per-generation artifacts (each generation has its own tag embeddings / EPA basis) or shared at KB level? Per-generation is cleaner; shared is cheaper.
- Q7 incremental rebuild after swap: when active=g2, dirty docs added to KB build incrementally on g2. Confirmed; mention explicitly so reviewers don't miss.
- Q8 `build-shadow` request body: does it specify the new versions (parser/chunker/embedder), or is that pulled from current `Settings` at call time? Implications for hot-reload semantics.

## Requirements

- chunk_id derivation continues to be embedder-free; confirmed by regression test.
- Qdrant point id transitions to `vector_point_id`; new and old embedder vectors can coexist in different generations without id collision.
- KB directory layout migrates to `{kb_root}/g{N}/...` with `meta.json` pointer; existing KBs migrate without data loss (mechanism per Q1 decision).
- Shadow build does not affect active reads; active reads always go to `meta.json.active_generation`.
- Swap is a single-write operation on `meta.json` via the existing atomic write primitive; reversible until retire.
- Retire deletes the retired generation's files and Qdrant collection; not reversible.
- Admin API endpoints exist with proper auth and structured error responses; status endpoint reports build progress.
- Trigger conditions: changing any of the named version fields enforces shadow build; in-place writes for content-only changes preserved.
- All existing tests pass; new tests cover migration, shadow build, swap, retire, ID coexistence.

## Acceptance Criteria

- [ ] **Eval slice named** (per [[eval-as-driver-mechanism]]): which fixtures will be replayed against shadow before swap? Naming required before `task.py start`.
- [ ] `chunk_id` does not contain `embedding_model_id` or `embedding_model_version`; covered by a regression test.
- [ ] `vector_point_id = hash(chunk_id, embedding_model_id, embedding_model_version)` is the Qdrant point id; covered by a unit test that two different embedder versions produce two different point ids for the same chunk.
- [ ] `collection_name(prefix, kb, generation)` produces `{prefix}_{kb}_g{N}`; existing call sites updated; safe character handling preserved.
- [ ] `{kb_root}/meta.json` exists for every KB after migration; contains `active_generation`, optional `shadow_generation`, `history[]`.
- [ ] `build_kb_incremental` (or its wrapper) accepts a target generation id and writes into `g{N}/` only; never overwrites another generation's files.
- [ ] `AppState` exposes `active_state` and optional `shadow_state` per KB; existing `swap_kb` continues to work for active swaps; new method documented for generation swap.
- [ ] 4 admin endpoints exist with auth + tests: `POST /admin/generation/build-shadow`, `POST /admin/generation/swap`, `POST /admin/generation/retire`, `GET /admin/generation/status`.
- [ ] Trigger condition enforcement: rebuild attempts that change a generation-trigger field on the active generation are rejected with a structured error pointing to `build-shadow`.
- [ ] Existing single-collection KBs migrate via the agreed mechanism; one integration test covers the migration path with a pre-existing fixture.
- [ ] All existing tests pass; eval slice replay shows no regression vs current baseline (per Acceptance #1).
- [ ] `architecture.md` Appendix B (Changelog) is NOT modified — A1+A4 are already in the body; no doc revision needed unless a contract changes during implementation.

## Out of Scope

- Real-flow traffic split (architecture-v2 D5: deferred indefinitely).
- T5 replay tool implementation (separate task; for this task, ad-hoc scripting against `search-feedback.jsonl` is acceptable for the eval slice).
- T2 QueryPlan / Reranker / `/answer` work.
- Any change to `architecture.md` (this task implements the spec, doesn't modify it).

## Research References

- `.trellis/spec/backend/architecture.md` § A1, § A4
- Memory: [[architecture-living-doc-location]], [[architecture-v2-followup-roadmap]], [[eval-as-driver-mechanism]], [[arch-vendor-specifics-discipline]]
- Code: `src/tagmemorag/chunk_identity.py`, `src/tagmemorag/storage/qdrant_vector.py`, `src/tagmemorag/state.py`, `src/tagmemorag/incremental_rebuild.py`, `src/tagmemorag/storage/atomic.py`
