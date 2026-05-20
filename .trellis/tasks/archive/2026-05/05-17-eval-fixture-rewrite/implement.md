# Implementation Plan — Phase A: coffee.jsonl 重标注

> 父文档：[prd.md](./prd.md) · [design.md](./design.md)
> 顺序约束：1 → 2 → 3 → 4 → 5 → 6 →（review gate）→ 7 → 8 → 9
> 6 步之前都是工具准备 + 候选生成；7-9 是你 review + 落地 + 验收。

## Checklist

### Stage 0：环境前置 / 影响面核查

- [ ] 顺手 grep `tests/fixtures/eval` 在哪些非 baseline 路径被引用（diag 脚本 / docs / spec）；预期 diag 不读 eval/*.jsonl，确认即可。
- [ ] 备份当前 baselines 到 task research 目录（`hashing-pre-rewrite-snapshot.json` / `siliconflow-pre-rewrite-snapshot.json`），便于 D6 sanity check 比对。

### Stage 1：写 relabel_eval_fixture.py

- [ ] 新增 `scripts/relabel_eval_fixture.py`：
  - argparse：`--suite` / `--docs` / `--top-k`（默认 10）/ `--output` / `--extra-candidates`。
  - 加载 eval suite (`load_eval_suite`)。
  - 构建双 KB（hashing tempdir + siliconflow tempdir），复用 `build_eval_baseline._build_config` + `state.build_kb`。
  - 对每条 query 跑 hashing + siliconflow wave_search top-K，并集去重（按 source_file + header 去重）。
  - extra-candidates 解析（"file:header,file:header"），加入候选列表标 `source="extra"`。
  - 输出 `<output>` 一条 query 一行 ProposalRecord JSON。
  - 重试包装：siliconflow encoder 调用走 `build_eval_baseline._with_retry`（注意 KB build 时 batch encode 也要包，避免半成品）。
- [ ] 新增最小单测 `tests/unit/test_relabel_eval_fixture.py`（无网络）：dedupe 逻辑、extra-candidates 解析、ProposalRecord schema。

### Stage 2：跑 coffee.jsonl 的 proposals

- [ ] 备份当前 hashing.json + siliconflow.json 到 `research/*-pre-rewrite-snapshot.json`（Stage 0 已做就跳过）。
- [ ] 跑 `python scripts/relabel_eval_fixture.py --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --output .trellis/tasks/05-17-eval-fixture-rewrite/research/coffee-proposals.jsonl`
- [ ] 验证输出有 7 条 ProposalRecord，schema 正确。

### Stage 3：AI 建议（Claude session 内）

- [ ] 把 `coffee-proposals.jsonl` 内容贴进对话，我对每条候选给 `relevant/borderline/not_relevant + 1 句理由`。
- [ ] 我在 `research/coffee-review.md` 内为每 query 起草决策块（候选清单 + AI 建议 + 留空"人工决定"）。

### Stage 4：人工 review（你来）

- [ ] 你逐条 review `coffee-review.md`，填"人工决定"部分。
- [ ] 标 dropped query（如果有）+ 原因。
- [ ] 标 extra-candidates（如果发现 AI 都漏的答案，回 Stage 2 加 `--extra-candidates` 重跑，迭代）。

### Stage 5：落地 fixture 修改

- [ ] 按 review 决策重写 `tests/fixtures/eval/coffee.jsonl`：
  - 扩 `relevant`。
  - 删 `min_*` 字段。
  - 删 dropped query 的整行。
- [ ] 跑 `pytest tests/unit/test_eval_dataset.py` 确认 schema 解析无报错。

### Stage 6：重 capture 双 baseline

- [ ] `python scripts/build_eval_baseline.py --embedder hashing --output tests/fixtures/eval/baselines/hashing.json --compare-with .trellis/tasks/05-17-eval-fixture-rewrite/research/hashing-pre-rewrite-snapshot.json`
- [ ] **D6 Sanity check**：检查 stdout delta 表，hashing 任意 suite 任意 metric 不下跌超过 0.05。如果跌了 → 回 Stage 4 修 review。
- [ ] `python scripts/build_eval_baseline.py --embedder siliconflow --output tests/fixtures/eval/baselines/siliconflow.json --compare-with .trellis/tasks/05-17-eval-fixture-rewrite/research/siliconflow-pre-rewrite-snapshot.json`
- [ ] 把两份 delta 表存档到 `research/baseline-delta-after-rewrite.txt`，commit 时引用。

### Stage 7：验收 gate

- [ ] `pytest tests/` — 必须 445/445 passed。
- [ ] `scripts/run_eval_ci.py`（默认 hashing）— 必须 8/8 绿。
- [ ] `scripts/run_eval_ci.py --baseline tests/fixtures/eval/baselines/siliconflow.json --embedder siliconflow --no-default-thresholds` — 必须 8/8 绿。

### Stage 8：文档同步

- [ ] `docs/wave-phase1-architecture.md` baseline 段加一句："coffee.jsonl 已对齐生产 embedder（Phase A），剩余 7 套 suite 见 wave-readiness-fixture-phase-b。"
- [ ] commit message 引用 baseline-delta-after-rewrite.txt 的 hashing-pre vs hashing-post + siliconflow-pre vs siliconflow-post。

### Stage 9：commit + Phase B 衔接

- [ ] 单 commit，stage 所有改动 + research 目录。
- [ ] commit message 末尾点出 Phase B 接力 calibration（候选数、阈值删除、dropped 标准、AI 建议平均准确率）。

## Validation

```bash
# Stage 1
.venv/bin/python -m pytest tests/unit/test_relabel_eval_fixture.py

# Stage 2
.venv/bin/python scripts/relabel_eval_fixture.py \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --output .trellis/tasks/05-17-eval-fixture-rewrite/research/coffee-proposals.jsonl

# Stage 5
.venv/bin/python -m pytest tests/unit/test_eval_dataset.py

# Stage 6
.venv/bin/python scripts/build_eval_baseline.py --embedder hashing \
  --output tests/fixtures/eval/baselines/hashing.json \
  --compare-with .trellis/tasks/05-17-eval-fixture-rewrite/research/hashing-pre-rewrite-snapshot.json
.venv/bin/python scripts/build_eval_baseline.py --embedder siliconflow \
  --output tests/fixtures/eval/baselines/siliconflow.json \
  --compare-with .trellis/tasks/05-17-eval-fixture-rewrite/research/siliconflow-pre-rewrite-snapshot.json

# Stage 7
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
.venv/bin/python scripts/run_eval_ci.py \
  --baseline tests/fixtures/eval/baselines/siliconflow.json \
  --embedder siliconflow --no-default-thresholds
```

## Review Gates

- **Gate A (Stage 4 后)**：人工 review 完成；review.md 每条 query 有"人工决定"段。
- **Gate B (Stage 6 后)**：D6 sanity check 通过（hashing 不退化超过 0.05）；如失败必须回 Stage 4 修。
- **Gate C (Stage 7 后)**：三项验收命令全绿。
- **Gate D (Stage 9 前)**：commit message 含双 delta 表 + Phase B 衔接备注。

## Rollback Points

- Stage 1-2：脚本 / proposals 出问题 → 单文件 revert / 删除重写。
- Stage 5-6：fixture 写飞 → git checkout HEAD -- tests/fixtures/eval/coffee.jsonl 回到旧 fixture。
- Stage 7 失败：分析 fail 原因 → 大概率回 Stage 4 修 review.md → 重 Stage 5-7。
- 极端情况（baseline sanity 反复失败）：放弃 Phase A，把任务降级为"工具链就绪 + 候选清单存档但不改 fixture"，留给 Phase A.1 再做。
