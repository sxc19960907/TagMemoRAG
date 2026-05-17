# Implementation Plan — wave-readiness-flags

> 父文档：[prd.md](./prd.md)

## Stages

### Stage 1: 写 diag 脚本

- [ ] `scripts/diag_wave_readiness_flags.py`：
  - 5 配置 × 4 strict siliconflow suite × 4 metric = 80 data points
  - 输出 diff 表（diff vs baseline）+ 推荐决议 (per flag pass/fail D3 判据)
  - 复用 `build_eval_baseline._smoke_check_siliconflow` + `_with_retry`
  - 复用 `build_eval_baseline._build_config(EMBEDDER_SILICONFLOW)`，再叠加 wave_phase1 flag
- [ ] 跑通后 stdout 归档到 `research/readiness-flags-diff.txt`

### Stage 2: 决策

- [ ] 基于 diff 表写 `research/readiness-decision.md`：
  - 3 个 flag 每个一节：实测 delta 表 + D3 判据评估 + 决议 (keep_off / flip_on)
  - 总结表
- [ ] 用户 review（autonomous mode 默认接受 AI 建议）

### Stage 3: 实施（如需翻开）

- [ ] 对决议为 flip_on 的 flag，改 `src/tagmemorag/config.py` 默认值
- [ ] 检查现有 baseline invariance e2e 测试是否需要调整断言：
  - `tests/e2e/test_search_baseline_invariance.py` 应该测的是"flag-off"路径，与翻开默认无关 → 应保持
  - 但如果它读 settings 默认值再做 search，可能会受影响 → 实测后判定
- [ ] 重 capture 两个 baseline (因为默认 flag on 后 search 行为变了)：
  - 备份当前 baseline 到 `research/{hashing,siliconflow}-pre-flip-snapshot.json`
  - 跑 build_eval_baseline 重出
- [ ] pytest 全量
- [ ] run_eval_ci 双路径（hashing default + siliconflow with informational）

### Stage 4: 文档 + commit

- [ ] README + docs/wave-phase1-architecture.md 标注新默认值
- [ ] commit message 含 diff 表 + 决议 + 翻开影响

## Validation

```bash
# Stage 1
.venv/bin/python scripts/diag_wave_readiness_flags.py \
  --output .trellis/tasks/.../research/readiness-flags-diff.txt

# Stage 3
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
.venv/bin/python scripts/run_eval_ci.py \
  --baseline tests/fixtures/eval/baselines/siliconflow.json --embedder siliconflow \
  --informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl
```

## Review Gates

- **Gate A (Stage 1 后)**：diag 脚本输出完整、可读、含 D3 判据评估列。
- **Gate B (Stage 2 后)**：决议落地到 readiness-decision.md，每个 flag 有结论。
- **Gate C (Stage 3 后)**：三项验收命令全绿；hashing CI 不漂；siliconflow informational 不超过 4 套。
