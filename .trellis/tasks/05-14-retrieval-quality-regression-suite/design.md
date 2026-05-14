# Design — 检索质量回归测试集

## 目的

把 PRD 的 5 个 MVP 项落到模块级契约和数据契约，给 implement.md 提供可执行的步骤蓝图。

## 模块边界

```
┌───────────────────────────────────────────────────────────────┐
│ tests/fixtures/eval/                                          │
│  coffee.jsonl (existing, untouched)                           │
│  product_manuals.jsonl (existing, untouched)                  │
│  fault_codes.jsonl       ┐                                    │
│  mixed_language.jsonl    │                                    │
│  model_numbers.jsonl     │ M1 new                             │
│  tag_cooccurrence.jsonl  │                                    │
│  cross_kb_negatives.jsonl│                                    │
│  tag_rerank_edge.jsonl   ┘                                    │
│  baselines/hashing.json   ─ M3 produced by build_eval_baseline│
│  baselines/siliconflow.json ─ M3, sanity only                 │
└─────────────────┬─────────────────────────────────────────────┘
                  │
┌─────────────────▼─────────────────────────────────────────────┐
│ src/tagmemorag/eval/                                          │
│  dataset.py     ── parse `negatives` field (M2)               │
│  matching.py    ── match_negatives()       (M2)               │
│  runner.py      ── apply baseline -2% suite thresholds (M3)   │
│                 ── propagate negative violations (M2)         │
│  report.py      ── output negative_hits in case report (M2)   │
└─────────────────┬─────────────────────────────────────────────┘
                  │
┌─────────────────▼─────────────────────────────────────────────┐
│ scripts/                                                      │
│  build_eval_baseline.py  ── M3                                │
│  eval-siliconflow.sh     ── M5                                │
└─────────────────┬─────────────────────────────────────────────┘
                  │
┌─────────────────▼─────────────────────────────────────────────┐
│ .github/workflows/quality.yml  ── M4                          │
└───────────────────────────────────────────────────────────────┘
```

## 数据契约

### Case schema 扩展（向后兼容）

现有 case 形状（dataset.py 的 `EvalCase` dataclass）保留，加 `negatives` 字段：

```jsonl
{
  "id": "fridge-vs-washer-noise",
  "kb_name": "default",
  "query": "compressor noise loud humming",
  "relevant": [
    {"source_file": "refrigerator/refrigerator_nrk6192.md", "header": "Compressor Noise", "text_contains": ["humming"]}
  ],
  "negatives": [
    {"source_file_prefix": "washer/", "metadata": {"product_category": "washer"}}
  ],
  "tags": ["semantic", "negatives"],
  "min_recall_at_k": 0.5
}
```

`negatives` 复用 `ExpectedRelevance` 的字段集合：`source_file` / `source_file_prefix` / `header` / `text_contains` / `metadata`。**任意一条 negative match 任意 top-K 结果 → case fail**（OR 关系）。

### Baseline JSON

```json
{
  "embedder": "hashing",
  "captured_at": "2026-05-14T08:30:00Z",
  "config_hash": "sha256:...",
  "thresholds_applied": {"floor_delta": 0.02},
  "suites": {
    "coffee.jsonl":           {"precision_at_k": 0.71, "recall_at_k": 0.92, "mrr": 0.85, "hit_at_k": 0.95},
    "product_manuals.jsonl":  {"precision_at_k": 0.65, "recall_at_k": 0.88, "mrr": 0.78, "hit_at_k": 0.92},
    "fault_codes.jsonl":      {...},
    "mixed_language.jsonl":   {...},
    "model_numbers.jsonl":    {...},
    "tag_cooccurrence.jsonl": {...},
    "cross_kb_negatives.jsonl":{...},
    "tag_rerank_edge.jsonl":  {...}
  }
}
```

`config_hash` = sha256 over (embedder + dim + parser config + search config + KB fixture file mtimes)。变化即触发"基线可能需要重跑"的人工 review。

### CI 加载顺序

```
runner 启动:
  1. 读 baselines/<embedder>.json
  2. 对每个 suite: threshold_i = max(baseline_i - 0.02, configured_min_i)
  3. 用合并后的 thresholds 跑 run_eval
  4. 报告里同时输出 baseline_value, applied_threshold, observed
```

## 关键代码点

### M2. dataset.py 扩展
- `EvalCase` 增加 `negatives: tuple[ExpectedRelevance, ...] = ()`
- `_parse_relevant(item)` 抽出，复用为 `_parse_relevance_list(items, field_name)`
- `load_eval_suite` 解析两个字段

### M2. matching.py 新增
```python
def match_negatives(
    results: Sequence[Result],
    negatives: Sequence[ExpectedRelevance],
) -> list[NegativeHit]:
    hits: list[NegativeHit] = []
    for rank, result in enumerate(results, 1):
        for neg_index, negative in enumerate(negatives):
            if _matches(result, negative):
                hits.append(NegativeHit(rank=rank, negative_index=neg_index, source_file=result.source_file))
    return hits
```

`NegativeHit` 是新 dataclass，字段：`rank, negative_index, source_file`。

### M2. runner.py 失败聚合
现有 `_threshold_failures` 不变；新增：
```python
def _negative_violations(hits: list[NegativeHit]) -> list[str]:
    return [f"negative #{hit.negative_index} matched at rank {hit.rank} ({hit.source_file})" for hit in hits]
```
case `failures` = threshold_failures + negative_violations（先 negatives 后 thresholds，便于 debug）。

### M2. report.py 字段
case-level report 增加：
- `negative_hits`: list of `{rank, negative_index, source_file}`
- 旧字段全保留

### M3. build_eval_baseline.py
```python
# scripts/build_eval_baseline.py
def main(embedder_kind: str, output: Path) -> None:
    cfg = _load_config_for(embedder_kind)  # hashing or siliconflow
    suites = sorted((Path("tests/fixtures/eval").glob("*.jsonl")))
    suite_metrics = {}
    for suite_path in suites:
        if suite_path.name == "baselines": continue
        report = run_eval(...)
        suite_metrics[suite_path.name] = report.aggregate.to_dict()
    output.write_text(json.dumps({
        "embedder": embedder_kind,
        "captured_at": _utc_now(),
        "config_hash": _config_hash(cfg, suites),
        "thresholds_applied": {"floor_delta": 0.02},
        "suites": suite_metrics,
    }, sort_keys=True, indent=2, ensure_ascii=False))
```

确定性：
- hashing embedder（dim=64，stable hash）
- 跑 eval 前固定 numpy seed（`np.random.seed(0)`，wave_search 内部如果用了 RNG 需要传入；当前实现是确定性的）
- output 用 `sort_keys=True`

### M4. CI workflow

```yaml
# .github/workflows/quality.yml
name: Quality CI
on:
  pull_request:
  push:
    branches: [master]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - name: pytest
        run: uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
      - name: eval suites
        run: uv run python scripts/run_eval_ci.py
```

`scripts/run_eval_ci.py`: 加载 baselines/hashing.json，对每个 suite 跑 `tagmemorag eval run` 并应用 -2% threshold；任意 fail 则 exit 1。

### M5. SiliconFlow sanity

```bash
# scripts/eval-siliconflow.sh
#!/usr/bin/env bash
set -euo pipefail
: "${SILICONFLOW_API_KEY:?need SILICONFLOW_API_KEY}"
exec uv run python scripts/build_eval_baseline.py \
    --embedder siliconflow \
    --output tests/fixtures/eval/baselines/siliconflow.json
```

跑完 diff 工作树（`git diff -- tests/fixtures/eval/baselines/siliconflow.json`），如果有变化提示 review。

## 失败/降级策略

- **negatives 命中**：case 直接 fail，不抑制 metric 计算（仍计入 report）
- **baseline 文件缺失**：CI fail，message 引导 `python scripts/build_eval_baseline.py`
- **config_hash mismatch**：CI WARNING（不 fail），引导手动重跑 baseline + review
- **SiliconFlow 网络失败**：本地脚本 print 错误退出非零；CI 不依赖

## 兼容性 / 回滚

- 现有 `coffee.jsonl` / `product_manuals.jsonl` 不动 → `test_eval_cli.py` 现有断言不受影响
- `EvalCase.negatives` 默认空 tuple → 老 case 行为不变
- `report` 老字段保留，新加 `negative_hits` 字段（向后兼容 - 老消费者忽略即可）
- 回滚整个任务 = revert 所有 commit + 删 baselines 目录 + 删 .github/

## 不确定事项 → 实施时决策

1. baseline -2% 的 floor 还是 case-level threshold 的 max？implement Step 3 时确认
2. SiliconFlow 跑出的 baseline 与 hashing 差距多大可接受？implement Step 5 时记录第一次跑的实际 diff，写进 docs
3. 是否需要 `--strict-config-hash` 模式让 CI 在 hash 不一致时直接 fail？暂不做，先 WARNING
