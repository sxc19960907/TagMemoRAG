# Implementation Plan — Phase 4 V8 geodesicRerank

> 父文档：[prd.md](./prd.md) · [design.md](./design.md)
> 顺序约束：1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 →（review）→ 9 → 10
> 每个阶段独立 commit，便于逐项 baseline diff 验证。

## Checklist

### 1. Settings + 配置校验（不可破坏 baseline）

- [ ] `src/tagmemorag/config.py`（或 settings 模块）`WavePhase1Settings` 加 4 个字段：
      `geodesic_rerank_enabled / geodesic_alpha / geodesic_oversample_factor / geodesic_min_geo_samples`，默认值见 design §7。
- [ ] 字段校验器：alpha clamp 到 [0, 1]，oversample_factor ≥ 1.0，min_geo_samples ≥ 1。
- [ ] 单测：`tests/unit/test_config.py` 加越界 / 默认值 / clamp 测试。
- [ ] 验证：默认配置加载产物字节等价于 master（diff 输出空）。

### 2. `TagBoostInfo.accumulated_energy` 字段

- [ ] `src/tagmemorag/wave_tag_spike.py` `TagBoostInfo` 加 `accumulated_energy: Mapping[int, float] | None = None`。
- [ ] `apply_tag_boost`：spike 成功路径 `info_extra["accumulated_energy"] = MappingProxyType(dict(spike_result.accumulated_energy))`；所有 skipped 路径不需要显式赋值（默认 None）。
- [ ] `to_dict` / debug payload：把 raw dict 排除，新增 `geodesic_energy_field_size: int` 字段（用 `len(accumulated_energy or {})`）。
- [ ] 单测 `tests/unit/test_apply_tag_boost.py`：
  - spike 成功路径 info.accumulated_energy 非 None 且 size > 0；
  - spike_disabled / matrix_missing / no_seeds 等所有 skipped 路径 info.accumulated_energy is None；
  - debug payload 不包含 raw dict 但包含 size。

### 3. `wave_search` 加 `rerank_pool_size` 参数

- [ ] `src/tagmemorag/wave_searcher.py` `wave_search` 签名加 `rerank_pool_size: int | None = None`。
- [ ] 排序后截断逻辑：None ⇒ 截 top_k（现状）；非 None ⇒ 截 `rerank_pool_size`。
- [ ] 单测 `tests/unit/test_graph_wave.py`：
  - `rerank_pool_size=None` 与现状字节相等；
  - `rerank_pool_size > top_k` 返回 `rerank_pool_size` 个候选；
  - `rerank_pool_size < top_k` 返回 `rerank_pool_size` 个候选（语义但调用方约定不该这么传）。
- [ ] 验证：`pytest tests/unit/test_graph_wave.py tests/e2e/test_search_baseline_invariance.py` 全绿。

### 4. `geodesic_rerank` 算法本体

- [ ] 新模块 `src/tagmemorag/wave_geodesic_rerank.py`：
  - `GeodesicRerankResult` dataclass（design §2.2）。
  - `geodesic_rerank(...)` 函数（design §3 伪代码）。
  - `_resolve_chunk_tag_ids(graph, node_id, *, kb_name, settings)` helper（design §2.3）。
  - `_score_aggregator(total, hits)` 内部函数（写死 `total/hits`，留扩展点注释）。
  - `_zero_swaps()` helper 返回 `{"rank_changed": 0, "new_entry": 0, "lost_entry": 0}`。
- [ ] 单测 `tests/unit/test_geodesic_rerank.py`（覆盖三层防御 + 主路径）：
  - `test_energy_field_empty_returns_input_order`（L0）；
  - `test_no_candidates_returns_empty`；
  - `test_hit_count_below_min_samples_zeros_geo`（L1）；
  - `test_max_geo_zero_returns_input_order_with_skip_reason`（L2）；
  - `test_alpha_zero_pure_knn_order_preserved`；
  - `test_alpha_one_pure_geo_reorders_by_normalized_geo`；
  - `test_swap_kinds_classifies_rank_changed_new_lost_correctly`；
  - `test_diagnostic_fields_attached_to_results`（geo_score/normalized_geo/geo_hit_count/original_knn_score）；
  - `test_metadata_tags_resolution_skips_unknown_tags`；
  - `test_input_candidates_not_mutated`。

### 5. Observability — metrics

- [ ] `src/tagmemorag/observability.py`（或对应 metrics 模块）：
  - `record_geodesic_rerank_applied(kb_name)`；
  - `record_geodesic_rerank_skipped(kb_name, reason)`；
  - `record_geodesic_rerank_swap(kb_name, kind, count)`；
  - `record_geodesic_rerank_hit_count(kb_name, hit_count)`（Histogram）。
- [ ] reason 白名单（design §6）加入 allowed label set（如有 enum / 校验逻辑）。
- [ ] 单测 `tests/unit/test_observability_metrics.py`：四个 recorder + 标签校验。

### 6. `execute_search` 接入

- [ ] `src/tagmemorag/search_runtime.py`：
  - 现有 `wave_search` 调用前增加 `v8_should_run` 判断（design §5）。
  - 走 V8 分支时：
    1. 计算 pool；2. 用 `rerank_pool_size=pool` 调 wave_search；3. 调 `geodesic_rerank`；4. 记录 metrics；5. 截 top_k。
  - flag-on 但前置不满足时：`_classify_skipped_reason(boost_info, ann_strategy)` 记 skipped。
  - flag-off 路径：维持 `wave_search(rerank_pool_size=None)`，不调 V8，不记 metric，**字节等价**。
- [ ] `SearchExecution` 是否需要新增字段？默认不加（V8 诊断走 metric + boost_info），但允许后续 follow-up 加 `geodesic_rerank_applied: bool`。
- [ ] 单测 `tests/unit/test_search_runtime_phase1.py`：
  - flag-off：完全字节等价；
  - flag-on + spike-off：silent noop + skipped(reason="spike_disabled")；
  - flag-on + spike 成功 + 充足候选：V8 跑通，metric 4 项都记录；
  - flag-on + spike 成功但 max_geo=0：silent noop + skipped(reason="max_geo_zero")；
  - flag-on + lexical-only 路径：silent noop + skipped(reason="lexical_only_path")；
  - filter 极严格使候选 < pool：V8 在实际候选上重排（不抛错）。

### 7. Lexical 兼容回归（D6.e）

- [ ] `tests/unit/test_geodesic_rerank.py::test_lexical_only_path_uses_metadata_tags`：
  lexical_source_k>0 + 向量路径退化时 V8 行为符合预期（要么 silent noop 要么在 lexical 候选上跑通）。
- [ ] `tests/unit/test_geodesic_rerank.py::test_hybrid_path_swap_metric_records`：
  ANN + lexical 混合候选下 swap_total 按预期分类。

### 8. Diag 脚本（D6.c）

- [ ] `scripts/diag_geodesic_rerank.py`：
  - 入参：`--kb`、`--queries-file`、`--alpha "0.0,0.1,0.3,0.5"`、`--min-samples "1,2,4"`、`--top-k`、`--oversample`。
  - 输出表格列：`alpha / min_samples / max_geo_zero_pct / applied_pct / avg_swap_count / hit_count_p50 / hit_count_p90 / recall_delta_vs_baseline`。
  - PASS gate：默认参数下 `max_geo_zero_pct < 50%` 且 `applied_pct > 0`，否则 exit 1（CI 显式提示）。
- [ ] 接入 `scripts/run_diag.sh`（如有）或独立 README 段落说明使用方法。
- [ ] 在本仓 fixture 上 smoke run 一次，把表格示例贴到 PR 描述。

### 9. Eval 接入（D6.d）

- [ ] 现有 8 套 hashing eval baseline + e2e baseline invariance：默认 off 路径**字节稳定**回归（CI 必绿）。
- [ ] 新增 enabled-on 列：模板复用 Phase 3 `pyramid+resonance` PASS gate 的写法，跑一组 `geodesic_rerank_enabled=true` + 默认 α/min_samples，输出 delta 表格。
- [ ] enabled-on 列**不强制** ≥ baseline 召回，仅记录 delta；进入 CI 看板，超阈值 (-5% 召回) 时 `pytest.warns` 提示。

### 10. 文档 + Spec 同步

- [ ] `README.md`：在 Phase 介绍段加 Phase 4 子章节，含公式、默认 off、α/min_samples 默认值差异、运维 reason 表格。
- [ ] `docs/wave-phase1-architecture.md`：加 Phase 4 段（与 Phase 3 段同结构）。
- [ ] `.trellis/spec/backend/database-guidelines.md` / `wave_phase1.spec.md`（如存在）：同步 4 个新 settings 字段。

## Validation

逐阶段验证（每个阶段提交前跑）：

```bash
# Stage 1 (settings)
pytest tests/unit/test_config.py

# Stage 2 (TagBoostInfo)
pytest tests/unit/test_apply_tag_boost.py tests/unit/test_wave_tag_spike_propagate.py

# Stage 3 (wave_search pool)
pytest tests/unit/test_graph_wave.py tests/e2e/test_search_baseline_invariance.py

# Stage 4 (algorithm)
pytest tests/unit/test_geodesic_rerank.py

# Stage 5 (metrics)
pytest tests/unit/test_observability_metrics.py

# Stage 6 (integration)
pytest tests/unit/test_search_runtime_phase1.py tests/e2e/test_search_baseline_invariance.py

# Stage 7 (lexical compat)
pytest tests/unit/test_geodesic_rerank.py tests/unit/test_lexical_search.py

# Stage 8 (diag)
python scripts/diag_geodesic_rerank.py --kb default --queries-file tests/fixtures/eval/queries.json --alpha 0.0,0.3 --min-samples 2

# Stage 9 (eval)
pytest tests/eval -k "baseline or geodesic"

# Stage 10 (docs)
# 手工 review；无自动校验。

# 全量回归
pytest
```

## Review Gates

- **Gate A（Stage 3 后）**：`rerank_pool_size=None` 路径与 master baseline 字节相等。任何 flag-off 路径 diff 即失败。
- **Gate B（Stage 6 后）**：flag-off 路径下 8 套 hashing eval baseline + e2e baseline invariance 字节稳定。
- **Gate C（Stage 9 后）**：enabled-on 列 PASS gate 跑通；diag 脚本在本仓 fixture 上 `applied_pct > 0`。
- **Gate D（Stage 10 后）**：文档 + spec 都同步；PR 描述包含 diag 表格 sample。

## Rollback Points

- 每个 stage 独立 commit；任意 stage 出问题，git revert 该 commit 即恢复。
- 极端情况：把 `geodesic_rerank_enabled` 设回 false 即可让所有 V8 代码路径 silent noop（即使代码已合并）。
- 不存在不可逆变更：无 schema migration、无 disk format 改动、无 deprecation。
