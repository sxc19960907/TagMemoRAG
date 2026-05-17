# Implementation Plan — Step B: PDF manual real eval

> 父文档：[prd.md](./prd.md) · [design.md](./design.md)

## Stages

### Stage 1: ingest 工具

- [x] 写 `scripts/ingest_real_manuals.py`：
  - 扫 `product_manuals/*.pdf` (root level)
  - 按 `_classify(filename)` 推断 category（D3 mapping + PDF 第一页 fallback）
  - 移动到 `product_manuals/<category>/<filename>.pdf`
  - 生成 `<filename>.metadata.json` sidecar 草稿
  - 幂等：已经在子目录的不重移
- [x] 跑：`.venv/bin/python scripts/ingest_real_manuals.py`
- [x] 验证：`product_manuals/<category>/` 下出现 5 份 PDF + 5 sidecar
- [x] 不写单测（一次性脚本，跑完即手工核对）

### Stage 2: build realmanuals KB

- [x] 写一个 `realmanuals.yaml` config 文件（在 task research 目录里，不进 repo 根）
- [x] 跑：`.venv/bin/python -m tagmemorag build --docs product_manuals --kb realmanuals --config <yaml>`
- [x] 验证：`data/realmanuals/` 下有 graph.json / vectors.npz / meta.json，chunk_count=527（略高于粗估但合理，来自 236 页 PDF + parser split/merge）

### Stage 3: 生成 fixture proposals

- [x] 复用 `scripts/relabel_eval_fixture.py` 流程：先手写一个空 query 集 `tests/fixtures/eval/realmanuals.jsonl`（12 query 草稿，relevant 为 placeholder；见 note）
- [x] **手写的 query 列表**（草稿，autonomous mode 直接做）：
  - 故障码（每 PDF 找 1-2 个）
  - 维护清洁（共 3-5 个）
  - 跨章节模糊（共 3-5 个）—— 命题靶子，对应原始 PRD 的"蒸汽很小"那种
- [x] 跑 relabel 工具生成候选 → research/realmanuals-proposals.jsonl
- [x] AI 起草 review.md → 用户 review（autonomous mode 默认接受）
- [x] 落地诊断用 fixture jsonl；正式 `text_contains` ground truth 暂缓，因为 top-K product routing 已暴露输入质量瓶颈，placeholder fixture 不进 CI

### Stage 4: diag 脚本

- [x] 写 `scripts/diag_realmanuals_eval.py`：
  - 4 配置（vec-only / wave-baseline / wave-residuals / wave-resonance）
  - 复用已 build 的 `realmanuals` KB，按 query 的 product tag 计算 top1/top3/top5 category routing metrics；不使用 placeholder matcher
- [x] 跑全 4 组 → 输出归档：`research/realmanuals-diag.txt`

### Stage 5: 报告

- [x] 起草 `research/realmanuals-eval-report.md`：含输入质量瓶颈、case 分析、后续建议
- [x] 命题判定：wave-baseline 与 vec-only 在 PDF page chunks 上持平；任务结论改为“无法证明算法优劣，先修 PDF→Markdown 结构化输入”

### Stage 6: 验收 + commit

- [x] pytest 全绿：`.venv/bin/python -m pytest tests/ -q` → 464 passed, 2 skipped
- [x] hashing CI 默认 8/8 strict 绿（不影响）：`.venv/bin/python scripts/run_eval_ci.py`
- [x] commit，含 ingest 工具 + diag 脚本 + fixture + 报告

## Completion Note

2026-05-17 follow-up: original AC expected fully reviewed `text_contains`
ground truth plus strict eval metrics. Real PDF top-K inspection showed a
more basic bottleneck first: category routing contamination from page-level
chunks. The task therefore closes with a reproducible routing diagnostic
(`scripts/diag_realmanuals_eval.py`) and archived output
(`research/realmanuals-diag.txt`) instead of promoting `realmanuals.jsonl`
to CI gating.

Latest routing diag over 12 queries and 527 chunks:

| config | top1 | top3 | top5 | mrr_cat |
|---|---:|---:|---:|---:|
| vec-only | 0.667 | 0.917 | 0.917 | 0.778 |
| wave-baseline | 0.667 | 0.917 | 0.917 | 0.778 |
| wave-residuals | 0.667 | 0.917 | 0.917 | 0.778 |
| wave-resonance | 0.667 | 0.917 | 0.917 | 0.778 |

Delta `wave-baseline - vec-only` is exactly 0.000 across all routing
metrics, supporting the report's recommendation: do PDF structural parsing
before more algorithm tuning.

## Validation

```bash
# Stage 1
.venv/bin/python scripts/ingest_real_manuals.py
ls product_manuals/*/*.pdf product_manuals/*/*.metadata.json

# Stage 2
.venv/bin/python -m tagmemorag build --docs product_manuals \
  --kb realmanuals --config <task_dir>/realmanuals.yaml
ls data/realmanuals/

# Stage 3
.venv/bin/python scripts/relabel_eval_fixture.py \
  --suite tests/fixtures/eval/realmanuals.jsonl \
  --docs product_manuals \
  --output <task_dir>/research/realmanuals-proposals.jsonl

# Stage 4
.venv/bin/python scripts/diag_realmanuals_eval.py \
  --reuse-built-kb \
  --output <task_dir>/research/realmanuals-diag.txt

# Stage 6
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
```

## Review Gates

- **Gate A (Stage 2 后)**：KB build 成功，chunk count 在合理范围，没有解析空白
- **Gate B (Stage 4 后)**：4 配置 diag 跑通，输出齐全
- **Gate C (Stage 5 后)**：报告含命题判定 + 数据 + 建议
- **Gate D (Stage 6 前)**：现有 CI 不漂

## Rollback

- 任意 stage 出问题，git stash + 独立 revert
- realmanuals KB 在 `data/realmanuals/` 独立目录，不影响 default
- 5 份 PDF 都是软件解析的，不修改源文件
