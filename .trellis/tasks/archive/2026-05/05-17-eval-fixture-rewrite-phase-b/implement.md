# Implementation Plan — Phase B

> 父文档：[prd.md](./prd.md) · [design.md](./design.md)

## 顺序（D4 优先级）

每套 suite 跑同一循环（Stage 1-4），全 7 套完成后跑一次 Stage 5-7 收尾。

## Per-suite Loop

For each suite in order: cross_kb_negatives → fault_codes → model_numbers → tag_cooccurrence → product_manuals → mixed_language → tag_rerank_edge

- [ ] Stage A: 跑 proposals
  ```bash
  .venv/bin/python scripts/relabel_eval_fixture.py \
    --suite tests/fixtures/eval/<NAME> \
    --docs <DOCS_FOR_SUITE> \
    --output .trellis/tasks/.../research/<NAME>-proposals.jsonl
  ```
  注：`coffee.jsonl` 用 `tests/fixtures`，其余用 `tests/fixtures/product_manuals`（与 SUITE_DOCS_OVERRIDES 一致）。

- [ ] Stage B: Claude 起草 review.md（含 relevant + negatives 两段）
- [ ] Stage C: 用户 review（默认接受 AI 建议）
- [ ] Stage D: 落地 fixture 修改

## Final Stages

- [ ] Stage 5: 双 baseline 重 capture
  ```bash
  python scripts/build_eval_baseline.py --embedder hashing \
    --output tests/fixtures/eval/baselines/hashing.json \
    --compare-with .trellis/tasks/.../research/hashing-pre-phase-b-snapshot.json
  python scripts/build_eval_baseline.py --embedder siliconflow \
    --output tests/fixtures/eval/baselines/siliconflow.json \
    --compare-with .trellis/tasks/.../research/siliconflow-pre-phase-b-snapshot.json
  ```

- [ ] Stage 6: 三项验收
  ```bash
  pytest tests/ -q
  python scripts/run_eval_ci.py
  python scripts/run_eval_ci.py --baseline tests/fixtures/eval/baselines/siliconflow.json --embedder siliconflow
  ```

- [ ] Stage 7: 文档更新 + commit + finish-work

## Sanity 兜底

如果某套 suite 的 review 在 negatives / relevant 处理上出现"灾难性重写"（>50% relevant 翻新），则单独切分 sub-task 讨论，不在 Phase B 内强推。

## Stage 0 (start of Phase B)

- [ ] 备份当前 baselines 到 `research/hashing-pre-phase-b-snapshot.json` / `research/siliconflow-pre-phase-b-snapshot.json`（Phase A 末态作为对照基线）。
