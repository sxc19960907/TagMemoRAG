# Implementation Plan — Step B: PDF manual real eval

> 父文档：[prd.md](./prd.md) · [design.md](./design.md)

## Stages

### Stage 1: ingest 工具

- [ ] 写 `scripts/ingest_real_manuals.py`：
  - 扫 `product_manuals/*.pdf` (root level)
  - 按 `_classify(filename)` 推断 category（D3 mapping + PDF 第一页 fallback）
  - 移动到 `product_manuals/<category>/<filename>.pdf`
  - 生成 `<filename>.metadata.json` sidecar 草稿
  - 幂等：已经在子目录的不重移
- [ ] 跑：`.venv/bin/python scripts/ingest_real_manuals.py`
- [ ] 验证：`product_manuals/<category>/` 下出现 5 份 PDF + 5 sidecar
- [ ] 不写单测（一次性脚本，跑完即手工核对）

### Stage 2: build realmanuals KB

- [ ] 写一个 `realmanuals.yaml` config 文件（在 task research 目录里，不进 repo 根）
- [ ] 跑：`.venv/bin/python -m tagmemorag build --docs product_manuals --kb realmanuals --config <yaml>`
- [ ] 验证：`data/realmanuals/` 下有 graph.json / vectors.npz / meta.json，chunk_count 合理（粗估 250-500 chunk）

### Stage 3: 生成 fixture proposals

- [ ] 复用 `scripts/relabel_eval_fixture.py` 流程：先手写一个空 query 集 `tests/fixtures/eval/realmanuals.jsonl`（10-15 query 草稿，relevant 留空待填）
- [ ] **手写的 query 列表**（草稿，autonomous mode 直接做）：
  - 故障码（每 PDF 找 1-2 个）
  - 维护清洁（共 3-5 个）
  - 跨章节模糊（共 3-5 个）—— 命题靶子，对应原始 PRD 的"蒸汽很小"那种
- [ ] 跑 relabel 工具生成候选 → research/realmanuals-proposals.jsonl
- [ ] AI 起草 review.md → 用户 review（autonomous mode 默认接受）
- [ ] 落地 ground truth 到 fixture jsonl

### Stage 4: diag 脚本

- [ ] 写 `scripts/diag_realmanuals_eval.py`：
  - 4 配置（vec-only / wave-baseline / wave-residuals / wave-resonance）
  - 单独的 KB load + run_eval per config（注意：`spike_enabled=false` 时不能与 `wave-baseline` 共享一个 KB build —— 需要确认 build 时的 wave settings 是否决定 KB 内容；如果决定就分别 build）
- [ ] 跑全 4 组 → 输出归档

### Stage 5: 报告

- [ ] 起草 `research/realmanuals-eval-report.md`：含 7 个必备段落（设计 §6）
- [ ] 命题判定（赢/平/输）+ 后续建议

### Stage 6: 验收 + commit

- [ ] pytest 全绿
- [ ] hashing CI 默认 8/8 strict 绿（不影响）
- [ ] 单 commit，含 ingest 工具 + diag 脚本 + fixture + 报告

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
  --output <task_dir>/research/realmanuals-eval.txt

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
