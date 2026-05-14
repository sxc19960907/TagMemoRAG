# Implement — 浪潮回归 Phase 0：tag 数据模型对齐

执行清单按依赖序排列。每一步都是可独立 commit 的小切片；遇到失败先回到上一个绿色点再继续。

## 前置检查（开始前）

- [ ] 已读 `prd.md` 的 D1-D5 决策与 5 项 MVP 工作项（M1-M5）
- [ ] 已读 `design.md` 的模块划分与数据契约
- [ ] 已读 `research/source-data-model.md` 的 schema 终稿（**M1 schema 名为 `manual_tags` 不是 `chunk_tags`**）
- [ ] 已读 `research/incremental-pca-feasibility.md` 的并发与原子写模式
- [ ] 当前分支干净，跑一次 `pytest` 全绿建立 baseline
- [ ] 已建立 `tests/e2e/test_search_baseline_invariance.py` 的 baseline 输出快照（AC6 锁底）

## 执行清单（按依赖序）

### Step 1: SQLite schema 三件套（M1）

- [ ] 1.1 修改 `src/tagmemorag/manual_registry.py` 的 `_init_schema`，增加 `tags` / `manual_tags` / `tag_intrinsic_residuals` 三张表 + 三个 index（schema 见 `design.md` 数据契约段）
- [ ] 1.2 在 `SQLiteManualRegistry` 上暴露 `connection()` 上下文管理（如不存在），供 tag_store 复用
- [ ] 1.3 写 `src/tagmemorag/tag_store.py`：定义 `upsert_canonical_tag`, `upsert_manual_tags`, `delete_manual_tags`, `find_orphan_tags`, `delete_tags`, `lookup_tag_id`, `iter_canonical_tags_with_vectors` 七个函数
- [ ] 1.4 写 `tests/unit/test_tag_store.py`：UNIQUE(kb,name) 约束、CASCADE、position 1-indexed 写入、orphan 检测
- [ ] 1.5 跑 `pytest tests/unit/test_tag_store.py -v`，全绿
- [ ] 1.6 跑 `pytest`（全套），无回归

**Validation**: `pytest tests/unit/test_tag_store.py tests/unit/test_manual_registry.py`
**Review gate**: schema 与 `research/source-data-model.md` 终稿 byte-for-byte 一致

### Step 2: Tag embedding 增量（M2）

- [ ] 2.1 写 `src/tagmemorag/tag_embedder.py`：`embed_dirty_tags(conn, kb_name, embedder)` 函数（design.md 算法段已给伪代码）
- [ ] 2.2 处理维度校验异常 `EmbeddingDimMismatchError`，定义在 `errors.py`
- [ ] 2.3 写 `tests/unit/test_tag_embedder.py`：幂等性（重跑只 skip）、batch 行为、维度不匹配处理、空 tag 列表无 op
- [ ] 2.4 修改 `src/tagmemorag/incremental_rebuild.py`：在 dirty manual 处理末尾追加 `tag_store.upsert_manual_tags` + `tag_embedder.embed_dirty_tags`
- [ ] 2.5 修改 `src/tagmemorag/state.py` 的 `RebuildTask`：增加 `tag_embeddings_added/skipped/failed` 字段
- [ ] 2.6 跑 `tests/integration/test_phase0_rebuild.py`：fixture build → 验证所有 canonical tags 有 vector

**Validation**: `pytest tests/unit/test_tag_embedder.py tests/integration/test_phase0_rebuild.py`
**Review gate**: 跑两次 build，第二次 `tag_embeddings_added=0, skipped>0`（AC3）

### Step 3: EPA basis（M3）

- [ ] 3.1 在 `pyproject.toml` 增加 `scikit-learn>=1.4`（依赖）
- [ ] 3.2 写 `src/tagmemorag/epa_basis.py`：
  - `epa_basis_lock(lock_path, timeout_sec)` 上下文（fcntl.flock）
  - `save_epa_basis(...)` / `load_epa_basis(path)`（atomic write 模式：tmp → fsync → replace → fsync(dir)）
  - `build_cold_start_basis(dim, K=8)`
  - `train_real_pca(tag_vectors, tag_names)`（KMeans + sklearn PCA + basisLabels by argmax cosine）
  - `retrain_if_needed(cfg, force=False)` 主入口
- [ ] 3.3 写 `src/tagmemorag/epa_projector.py`：纯读对象，提供 `project(query_vec)`（Phase 0 不接入检索，但单测要跑通）
- [ ] 3.4 写 `tests/unit/test_epa_basis.py`：
  - 冷启动路径：N<16 时 basis = identity[:K]，basisLabels = ["axis-0",...]
  - 真 PCA 路径：N≥16 时 train_kind="real-pca"，K 满足 cum_var≥0.95 且 ≥8
  - save/load roundtrip：所有字段保持
  - schema_version=1 加载 OK，version=2 抛错
  - graduation：先冷启动写一次，添加 tag 到 N≥16 后再训，train_kind 升级
- [ ] 3.5 写 `tests/unit/test_epa_concurrency.py`：
  - 双线程同时调 `retrain_if_needed`，验证锁串行化
  - 模拟 atomic write 中断：tmp 存在但 final 不存在，下次启动不读破损文件
- [ ] 3.6 修改 `incremental_rebuild.py`：rebuild 末尾调用 `epa_basis.retrain_if_needed(cfg)`
- [ ] 3.7 RebuildTask 增加 `epa_basis_train_kind / epa_basis_K / epa_basis_tag_count / epa_train_error` 字段
- [ ] 3.8 修改 `src/tagmemorag/cli.py`：增加 `tagmemorag epa rebuild [--force]` 子命令
- [ ] 3.9 在 `config.yaml` 增加 `wave_phase0` 段（紧急回滚开关 + 调参）
- [ ] 3.10 跑 e2e：4 个 fixture KB 跑 build → 验证 `data/_global/epa_basis.npz` 生成，train_kind="cold-start"（fixture 总 tag<16）

**Validation**: `pytest tests/unit/test_epa_basis.py tests/unit/test_epa_concurrency.py`
**Review gate**: AC2（fixture 上 cold-start 标记）+ AC7（构造 N≥16 验证 graduation）

### Step 4: tag_rewrite 接通 SQLite（M4）

- [ ] 4.1 修改 `src/tagmemorag/tag_governance.py` 的 `commit_tag_rewrite`：在写完 metadata.json 后追加 SQLite 同步段（design.md 已给伪代码）
- [ ] 4.2 处理 merge 的 conflict：用 `INSERT OR IGNORE` / `UPDATE OR IGNORE`，保留 target 的 position
- [ ] 4.3 末尾调用 `epa_basis.retrain_if_needed(cfg, force=True)`（taxonomy 变了必须重训）
- [ ] 4.4 写 `tests/unit/test_tag_governance_sqlite_sync.py`：rename / merge / delete 三种操作的 SQLite 状态对齐
- [ ] 4.5 跑 `pytest tests/unit/test_tag_governance*.py`，全绿（含旧测试不退化）

**Validation**: `pytest tests/unit/test_tag_governance_sqlite_sync.py tests/unit/test_tag_governance.py`
**Review gate**: AC4（rewrite 后 SQLite 与 metadata 状态一致）

### Step 5: Manual 删除级联（M5）

- [ ] 5.1 找到 manual delete 实际调用点（`api.py` 的 `DELETE /manuals/{id}` 或 `manual_library.delete_manual`），梳理现有路径
- [ ] 5.2 在 delete 末尾追加 SQLite 清理（design.md 伪代码）：
  - DELETE manual_tags WHERE kb_name=? AND manual_id=?
  - 找孤儿 tags（LEFT JOIN manual_tags）+ DELETE
- [ ] 5.3 标记 EPA dirty（不立即重训；rebuild 末尾批量处理）
- [ ] 5.4 RebuildTask 增加 `orphan_tags_removed` 字段
- [ ] 5.5 写测试：删除 manual → manual_tags 行清零 → 孤儿 tag 被识别 → 下次 rebuild 触发 EPA 重训

**Validation**: `pytest tests/unit/test_manuals_delete.py tests/integration/test_phase0_rebuild.py`
**Review gate**: AC5（manual 删除级联 OK）

### Step 6: 可观测性 + 文档

- [ ] 6.1 修改 `src/tagmemorag/observability/metrics.py`：增加 4 个 Prometheus 指标（design.md 列表）
- [ ] 6.2 修改 `src/tagmemorag/api.py`：rebuild 任务响应序列化包含新字段（向后兼容）
- [ ] 6.3 写 `docs/tag-ordering-convention.md`：明确 metadata.tags 数组顺序约定（D1）
- [ ] 6.4 在 `/manuals/validate` 端点加非阻塞警告：检测到 tag 顺序疑似无意义时提示用户
- [ ] 6.5 修改 `README.md`：加 Phase 0 章节，描述新 SQLite 表 + epa_basis 文件 + 紧急回滚开关。**不要暴露浪潮回归路线**（避免误导用户期待新检索能力）

**Validation**: 启动服务 → curl /metrics → 看到新指标
**Review gate**: README 不提"WAVE 算法"或"浪潮"字样，仅描述数据层变化

### Step 7: 回归 + 验收

- [ ] 7.1 跑 `tests/e2e/test_search_baseline_invariance.py`：execute_search 输出与 Phase 0 前 baseline 字节一致（AC6）
- [ ] 7.2 跑 `pytest`（全套），全绿
- [ ] 7.3 跑 lint + type-check（项目规范的命令）
- [ ] 7.4 删 SQLite 三表 + 删 epa_basis.npz，重启服务，跑健康探针 + /search → 无错（AC8 回滚验证）
- [ ] 7.5 重新跑 build → 三表与 npz 重新生成 → /search 仍正常
- [ ] 7.6 在 PR 描述里附 8 个 AC 的勾选状态

**Validation**: AC1-AC8 全部勾选
**Review gate**: 人工 review 整个 PR，重点看 schema 迁移、并发锁实现、tag_rewrite 同步逻辑

## 验收命令汇总

```bash
# 单测
pytest tests/unit/test_tag_store.py
pytest tests/unit/test_tag_embedder.py
pytest tests/unit/test_epa_basis.py
pytest tests/unit/test_epa_concurrency.py
pytest tests/unit/test_tag_governance_sqlite_sync.py

# 集成
pytest tests/integration/test_phase0_rebuild.py

# e2e
pytest tests/e2e/test_search_baseline_invariance.py

# 全套
pytest

# Lint / type-check（按项目实际命令）
# 例如：
# ruff check src/ tests/
# mypy src/

# CLI 烟测
tagmemorag build --docs tests/fixtures/product_manuals --kb test --config config.yaml
tagmemorag epa rebuild --force
sqlite3 data/manual_registry.sqlite3 "SELECT count(*) FROM tags; SELECT count(*) FROM manual_tags;"
ls -la data/_global/
```

## Review Gates（关键检查点）

每个 Step 末尾 review gate 不通过就不进入下一步。设计原则：

1. **Step 1 完成后**：schema 是 Phase 1+ 所有移植工作的地基。这一步错了后面全错。**慢一点没关系**。
2. **Step 3 完成后**：EPA basis 是首个跨 KB 全局资产，并发锁逻辑是新代码新模式，需重点 review。
3. **Step 7 的 AC6**：如果 search 输出有任何字节差异，说明 Phase 0 不小心动了检索路径，必须找出原因（hash 漂移 / dict 顺序 / 浮点累积），不能简单"接受新基线"。

## Rollback Points（回滚点）

每完成一步可独立 commit。回滚时按倒序 git revert：

1. Step 7 → 直接 revert（仅文档/可观测性变更）
2. Step 6 → revert（不影响功能）
3. Step 5 → revert（manual delete 回到只清 graph 不清 SQLite）
4. Step 4 → revert（tag_rewrite 回到只动 metadata，SQLite 残留 — **不一致，需要手动清理**）
5. Step 3 → revert + 删 `data/_global/`
6. Step 2 → revert（tag 表保留但无 vector）
7. Step 1 → revert + DROP TABLE 三张

**完整回滚**（紧急情况）：
```bash
git revert <step1-commit>..<step7-commit>
sqlite3 data/manual_registry.sqlite3 "DROP TABLE manual_tags; DROP TABLE tag_intrinsic_residuals; DROP TABLE tags;"
rm -rf data/_global/
```

## 总工作量估计

| Step | 估时 |
|---|---|
| Step 1 (schema + tag_store) | 0.5 天 |
| Step 2 (tag embedding) | 1 天 |
| Step 3 (EPA basis + 冷启动 + 并发) | 2 天 |
| Step 4 (tag_rewrite 同步) | 0.5 天 |
| Step 5 (manual 删除级联) | 0.5 天 |
| Step 6 (可观测 + 文档) | 0.5 天 |
| Step 7 (回归 + 验收) | 0.5 天 |
| **合计** | **5.5 天** |

PRD 之前估的 9-15 天是包含全部 Phase 0-5 的总和，本任务只是 Phase 0，落在合理范围。

## 不确定事项 → 实施时决策

design.md 末尾列的 4 个 open implementation questions：

1. `manual_registry.py` 的连接复用接口 → 实施 Step 1.2 时定，建议直接暴露 `_connect()` 改名为 `connection()`
2. `embedder.encode` 失败语义 → 实施 Step 2.1 时读 embedder.py 实际行为，按现状对齐
3. EPA 失败 metrics → Step 6.1 时加上，counter 名 `tagmemorag_epa_basis_retrain_failed_total`
4. tag upsert 在 graph swap 之前还是之后 → **建议之前**（tag 表是全局资产，graph swap 失败也希望 tag 数据已落盘；但 swap 前 fail 时 task.status 是 "failed" 不是 "done"，需明确语义）— 实施 Step 2.4 时和 incremental_rebuild 现有流程对齐
