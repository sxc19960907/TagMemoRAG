# 浪潮回归 Phase 0：tag 数据模型对齐

## Goal

把 manual.metadata.tags 从字符串数组提升为带 embedding 的一等公民数据，建立 tag↔chunk 的 position-aware 映射，为后续移植 VCPToolBox 的 TagMemoEngine（EPA / ResidualPyramid / applyTagBoost / SpikePropagation / geodesicRerank）准备数据基底。本任务只做底层数据模型，不动检索路径。

## Background / Known Context

### 项目本意
TagMemoRAG 立项目标是用 VCPToolBox 的浪潮算法（Wave v6/v7/v8）做产品说明书的语义检索。当前实现是浪潮算法的浅层近似 — 用 6 个手调 boost 旋钮（lexical/metadata/tag/exact_code/model）模拟源头的 tag-context 调制效果，丢失了源头算法的核心判别力。

### 浪潮算法的数据依赖（来自源头 VCPToolBox）
源头 `TagMemoEngine.applyTagBoost` 和 `geodesicRerank` 依赖以下数据：
- `tags(id, name, vector)` — tag 实体 + embedding，用于 query 调制和共现矩阵
- `file_tags(file_id, tag_id, position)` — position 决定共现序位势能 `phi = 0.9 - 0.4 * (pos-1)/(n-1)`
- `tag_intrinsic_residuals(tag_id, residual_energy)` — V7 虫洞张力的支撑（可后置）
- `chunks.file_id` — chunk 到 file 的反查映射

### TagMemoRAG 现状
- `manual_registry.sqlite3` 已有 `manual_records` 和 `manual_audit_events` 两张表，没有 tag 实体
- `tag_governance.py` 783 行做 canonical/synonym 治理，`CanonicalTag(tag, label, description)` 没有 vector 字段
- manual.metadata.tags 是字符串数组，无序、无 embedding、无共现关系
- Chunk dataclass 已有 `metadata: dict[str, Any]`，可挂 tag 关联但目前不挂
- chunk → manual_id 映射已存在（chunk.metadata 通过 graph_builder 挂载）

### 移植路线（Phase 0 是先决条件）
```
Phase 0  数据模型对齐                    ← 当前任务
Phase 1  共现矩阵 + V6 spike            ← 依赖 Phase 0
Phase 2a 简化 applyTagBoost (跳过 EPA)  ← 依赖 Phase 0
Phase 2b 完整 EPA + ResidualPyramid     ← 依赖 Phase 0
Phase 3  V7 虫洞 (intrinsic residuals)
Phase 4  V8 geodesicRerank
Phase 5  清理旧 boost 旋钮
```

## Assumptions (temporary, 待回答 Open Questions)

- 假设 2：EPA basis 全 KB 共享（以最大化跨 KB 语义可比性）
- 假设 3：tag embedding 复用现有 embedder（BAAI/bge-small-zh-v1.5, 384 维）
- 假设 4：tag 表与 manual_records 共存于同一 SQLite 文件（manual_registry.sqlite3）

## Resolved Decisions

### D1（已锁定）: tag 顺序语义 = 人工标注顺序，分两阶段落地

**决定**：采用 Approach A 的 schema（`position` 字段，按 `metadata.tags` 数组下标写入），但承认现存数据**暂时没有真实排序信号**。

**Phase 0 现在做**：
- chunk_tags 表加 `position INTEGER` 字段
- 写入时直接用 metadata.tags 的数组下标（A=1, B=2, C=3）
- 暂时不强制标注语义，等于在 V7 序位势能上跑"近似 LEGACY_PHI"的效果

**Phase 0 同时交付**：
- `docs/tag-ordering-convention.md` — 明确"新增 manual 时，tags 数组应按从具体到宽泛排序"（如 fault-code 在前、laundry 在后）
- 在 `/manuals/validate` 加一个**非阻塞警告**，提示标注顺序约定

**Phase 7+ 后续**：如 V7 上线后发现序位势能信号弱，再考虑用 LLM 辅助对存量 tag 做一次重排。schema 不变，仅数据回填。

**为什么不选 C（无序）**：C 写死 `position=0`，未来升级 V7 必须改 schema 又改数据；A 的 schema 是 V7-ready 的，即使现在信号弱，未来填进真实顺序也不需要迁移。

**为什么不选 B（文本首次出现）**：fixture 数据显示 tag 全是抽象概念（fault-code / maintenance-task / temperature-setting），字面不会出现在文本里，需依赖 synonym 反向匹配 — 复杂度高且对中英混合语料不稳定。

### D2（已锁定）: EPA basis = 全 KB 共享

**决定**：所有 KB 的 canonical tags 合并跑一次 PCA 得到全局 `orthoBasis`，存到 `data/_global/epa_basis.npz`（KB 维度无关的全局资产）。

**理由**：
- 当前 fixture 每 KB 仅 3 个 tag、embedding 384 维 — per-KB PCA 完全退化（样本数 << 维度数）
- 全局 basis 让小 KB 也能受益于全语料的语义分布
- 跨 KB 检索（即使现在不支持）未来一旦上线，basis 可比性是必要前提

**实现要点**：
- 用 `sklearn.decomposition.IncrementalPCA`，新 KB / 新 tag 加入时增量更新，避免每次全量重训
- basis 维度 K 暂定 8（源头默认值附近，可调）
- basis 训练触发时机：rebuild 完成且 `len(canonical_tags) >= K * 2` 时检查是否需要重训
- 提供 `tagmemorag epa rebuild` CLI 子命令做手动全量重训

**风险**：basis 偏向 tag 数多的 KB。后续如果某 KB 数据膨胀严重导致 basis 漂移，再考虑加权 PCA（按 KB 反向加权）。MVP 不做。

### D3（已锁定）: tag_intrinsic_residuals 表 = 建表但留空

**决定**：Phase 0 建 `tag_intrinsic_residuals(tag_id INTEGER PRIMARY KEY, residual_energy REAL NOT NULL DEFAULT 1.0)` 表，默认值 1.0（"无新颖度信号"），等 Phase 3 移植 ResidualPyramid 时再 INSERT。

**理由**：
- residual_energy 计算依赖 ResidualPyramid 算法本身，Phase 0 没移植，表填不出真实值
- 但 schema 在 Phase 0 一次到位，避免 Phase 3 时再做一次 manual_registry.sqlite3 迁移（生产表，迁移有风险）
- 默认值 1.0 让未来的 V7 虫洞张力公式 `tension = coocWeight * residual` 在 Phase 3 之前等价于"只看共现强度"，平滑降级

### D4（已锁定）: tag embedding 计算时机 = rebuild 时增量

**决定**：tag embedding 计算挂在 `incremental_rebuild` 的 dirty manual 处理路径上。

**实现要点**：
- 在 incremental_rebuild 处理 dirty manual 时多一步：对该 manual 涉及的 canonical tags，若 SQLite 中无 embedding 或 tag 文本变更，则调用 `Embedder.encode(batch)` 写回
- 复用 `config.model.batch_size`，不引入新配置
- tag 表是 graph-independent 的**全局资产**，rebuild swap 时不参与双缓冲（写入即生效，rebuild 失败也保留）
- upload/validate 路径不动 — upload 不阻塞在 embedder I/O 上

**理由**：upload 走"快路径"、rebuild 走"重路径"是现有架构铁律（参见 manual_library.py 设计），tag embedding 是重操作，必须在 rebuild 侧。

## Open Questions

（无 — 所有 Blocking/Preference 问题已锁定）

## MVP Scope (Expansion Sweep 收敛后)

Phase 0 范围明确为以下五件事，按依赖序：

### M1. SQLite schema 三件套
建表加到 `manual_registry.sqlite3`（幂等 `CREATE TABLE IF NOT EXISTS`），schema 终稿见 `research/source-data-model.md`：

- `tags(id, kb_name, name, vector BLOB, embedding_dim, embedded_at, UNIQUE(kb_name, name))`
- `manual_tags(kb_name, manual_id, tag_id, position, PRIMARY KEY(kb_name, manual_id, tag_id), FK tag_id ON DELETE CASCADE)` — 粒度对齐源头 file_tags（manual 级，不是 chunk 级），避免 chunk_count×tag_count 行膨胀
- `tag_intrinsic_residuals(tag_id PRIMARY KEY, residual_energy REAL DEFAULT 1.0, neighbor_count INTEGER DEFAULT 0, computed_at TEXT DEFAULT datetime('now'), FK tag_id ON DELETE CASCADE)`

注：`chunk_tags` 是早期命名，研究后改名为 `manual_tags`；`tag_intrinsic_residuals` 增补 `neighbor_count` 与 `computed_at`（源头有，PRD 早期遗漏）。

### M2. Tag embedding 增量计算
- 在 `incremental_rebuild` 处理 dirty manual 时，对涉及的 canonical tags 调用 `Embedder.encode(batch)` 写回 `tags.vector`
- 复用 config.model.batch_size；单事务写入，失败回滚
- bulk_import 路径同样适用（`manual_bulk_import.py` 走的是同一条 rebuild）

### M3. EPA basis 训练 + 冷启动降级
- 全 KB 共享 basis，存 `data/_global/epa_basis.npz`（含 `orthoBasis`, `basisMean`, `K`, `tag_count_at_train`, `train_kind`）
- 触发：rebuild 完成且 `len(canonical_tags_global) >= K*2` 时检查；首次或 tag 增量 > 20% 时跑 IncrementalPCA
- **冷启动降级**：tag 数 < K*2 时 basis = identity matrix（前 K 维），`train_kind="cold-start"`；后续 tag 增长到阈值后自动升级到真 PCA
- 全局锁：`data/_global/epa_basis.lock`（fcntl 文件锁，避免多 KB 并发 rebuild 写坏 basis）
- 提供 `tagmemorag epa rebuild` CLI 子命令做手动全量重训

### M4. tag_rewrite 接通 SQLite
- `commit_tag_rewrite` 同步操作 SQLite：
  - rename：UPDATE tags SET name=..., vector=NULL, embedded_at=NULL（清空 embedding 触发下次 rebuild 重算）
  - merge：UPDATE OR IGNORE manual_tags SET tag_id=target; DELETE source tag
  - delete：DELETE FROM tags WHERE id=...（CASCADE 自动清理 manual_tags 和 tag_intrinsic_residuals）
- 任何 tag 变更触发 EPA basis 立即重训（force=True）

### M5. Manual 删除级联清理
- `DELETE /manuals/{id}` 时清理 manual_tags 行
- 清理后检查 tags 表有无孤儿（无 manual_tags 引用的 tag），孤儿 tag 删除 + 标记 EPA dirty
- EPA dirty 在下次 rebuild 末尾批处理，避免高频删除时频繁重训

## Out of Scope（明确不做）

- query 调制层 `applyTagBoost` 实现（Phase 2a）
- 共现矩阵构建 `buildDirectedCooccurrenceMatrix`（Phase 1）
- spike propagation / 虫洞张力（Phase 1/3）
- ResidualPyramid 算法实现（Phase 2b；residual_energy 真实值在 Phase 3 填）
- geodesic rerank（Phase 4）
- 现有 6 个 boost 旋钮的清理（Phase 5）
- 检索质量回归测试集（独立任务，但建议在 Phase 1 之前完成）
- AppState 拆分、api.py 拆 router（独立工程债）
- 多语言 tag 翻译策略（未来演进，schema 不预留 language 字段；如需支持，另起 task）
- Synonym tag 的 embedding 化（未来演进，当前 tags 表只存 canonical）

## Requirements

1. **R1（数据层）**：Phase 0 的 SQLite schema 与已有 `manual_records` / `manual_audit_events` 共存，可在已有数据库上幂等迁移
2. **R2（embedding）**：tag embedding 计算路径与现有 chunk embedding 共用 Embedder 实例，不引入新依赖
3. **R3（EPA）**：EPA basis 训练对 fixture 数据规模（10-12 tags）必须可跑通 — 通过冷启动降级实现
4. **R4（一致性）**：tag_rewrite 和 manual 删除路径维护 SQLite 与 metadata 的强一致；EPA basis dirty 标记可观测
5. **R5（无行为变更）**：execute_search 的输出与 baseline 字节级一致 —— Phase 0 不读 tags 表参与检索
6. **R6（可回滚）**：删除三张 SQLite 表 + 删除 epa_basis.npz 即回到 Phase 0 之前状态
7. **R7（可观测）**：rebuild 任务的 task.impact_report 增加 `tag_embeddings_added/updated/skipped`、`epa_basis_train_kind`、`orphan_tags_removed` 字段

## Acceptance Criteria

- [ ] AC1：`pytest` 全套通过（含新增的 tag/EPA 单测）
- [ ] AC2：在 4 个 fixture KB（washer/dishwasher/ac/fridge）上跑 `tagmemorag build`，所有 canonical tags 都有 embedding，EPA basis 文件生成且 train_kind 标记为 cold-start
- [ ] AC3：跑两次重复的 build，第二次 `tag_embeddings_added=0, tag_embeddings_skipped=N`（增量幂等）
- [ ] AC4：触发 tag_rewrite（rename/merge/delete）后，SQLite tags 表与 metadata.json 状态一致；epa_basis dirty 标记正确
- [ ] AC5：删除 manual 后，manual_tags 行被清理；无引用的 tag 被识别为孤儿
- [ ] AC6：execute_search 在 fixture 上的输出与 Phase 0 之前的 baseline 字节级一致（用 snapshot test 锁住）
- [ ] AC7：构造 tag 数 < K*2 的场景，验证 EPA basis 走 cold-start 分支不抛错；构造 tag 数 ≥ K*2 的场景，验证升级到真 PCA
- [ ] AC8：删 SQLite 三表 + 删 epa_basis.npz，重启服务后所有功能正常（验证回滚路径）

## Definition of Done

- 数据库 schema 迁移完成且向后兼容（旧 manual_registry.sqlite3 可平滑升级）
- 所有现有测试不退化（pytest + lint + type-check 全绿）
- 新增 tag 表的 CRUD/embedding 路径有单测覆盖
- rebuild 流程里 tag embedding 步骤 + EPA basis 训练 + 冷启动降级 有 e2e 验证
- tag_rewrite / manual 删除的 SQLite 同步路径有单测覆盖
- 文档：在 README 增加 Phase 0 章节说明数据模型变更，不暴露浪潮回归路线（避免误导用户）
- 不引入对检索路径的任何行为变更（execute_search 输出与 baseline 字节级一致）

## Research References

待研究（design.md 之前需完成）：
- [ ] `research/source-data-model.md` — 源头 TagMemoEngine 的 SQLite schema（tags / file_tags / tag_intrinsic_residuals 完整字段）
- [ ] `research/epa-basis-training.md` — 源头 EPAModule 的 PCA basis 训练流程与维度选择
- [ ] `research/incremental-pca-feasibility.md` — sklearn IncrementalPCA + 冷启动降级方案

## Decision Log (ADR-lite)

- **D1**: tag 顺序 = 数组下标，配标注规范文档（详见 Resolved Decisions）
- **D2**: EPA basis = 全 KB 共享 + 冷启动降级
- **D3**: tag_intrinsic_residuals 表建表留空，默认 1.0
- **D4**: tag embedding 在 incremental_rebuild 时增量计算
- **D5**: tag_rewrite 接通 SQLite，manual 删除级联清理 — 纳入 Phase 0 MVP
