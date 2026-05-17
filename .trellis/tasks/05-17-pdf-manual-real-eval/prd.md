# Step B：用真 product_manuals PDF 实测浪潮算法 vs plain KNN

## Goal

把 `product_manuals/*.pdf` 5 份真生产说明书 ingest 进一个独立的 `realmanuals` KB，
然后实测两件事：

1. **浪潮算法 (spike on) vs plain KNN (spike off)** 在真数据上的相对效果
   — 这是设计文档**最初命题**的最直接验证（"图传播 vs KNN 哪个对客服 RAG 更好"）。
2. 在真数据上**重跑 wave-readiness-flags diag**，看 3 个 default-off flag
   (resonance / residuals / geodesic) 是否在更大数据规模下开始有信号。

## Background / Known Context

### 数据规模实证（已勘察）

| PDF | pages | total_chars |
|---|---|---|
| ASKO W6564.pdf | 28 | 13,205 |
| HISENSE BSA5221.pdf | 59 | 48,609 |
| HISENSE DHGA901NL.pdf | 63 | 58,113 |
| HISENSE DHQE800BW2.pdf | 55 | 8,946 |
| HISENSE HR6FDFF701SW.pdf | 31 | 53,363 |
| **总计** | 236 | 182,236 |

约**18 万字**，比 tests/fixtures 的 49 行多 ~300 倍。这是浪潮算法应该开始
发挥结构性优势的数据规模。

### 现有工具就绪

- ✅ PDF parser 已通过 `pypdf` 接通（`src/tagmemorag/parser.py:87 _parse_pdf`），
  每页一个 chunk，header=`Page N`，自动 split 长块、merge 短块
- ✅ `python -m tagmemorag build --docs <dir> --kb <name>` 已可用
- ✅ siliconflow Qwen3-VL HTTP embedder 已就绪
- ✅ run_eval_ci 双轨基础设施已就绪

### PDF parser 局限（实证发现，写入 PRD 作为本任务限制）

每页一个 chunk + header=`Page N` 意味着：
- 结构边降级到只剩 "连续"（兄弟/父子边失效，因为 header 是平面的）
- 浪潮算法的"图传播跨章节召回"优势**部分受限**——但仍能传播
- 这是**真实生产 PDF 输入的固有问题**，不是本任务要解决的（解决方向是 PDF→Markdown 章节切分，单独任务）
- 本任务接受这个限制，测的是"在 PDF 一页一 chunk 的现实结构下，wave 仍比 KNN 好吗"

### 与现有 KB 隔离

不动 `default` KB（fixture eval 还在用）。新 KB `realmanuals` 完全独立。

## Decisions

- **D1 用独立 KB `realmanuals`**：不污染 default KB，不影响现有 hashing CI。
- **D2 用 siliconflow Qwen-VL 4096 维**（生产配置一致）。
  - 不用 hashing 64 维：18 万字真数据上 hashing 自身已经太弱，对照失去意义
- **D3 metadata sidecar 自动生成**：
  - 写一个一次性脚本 `scripts/ingest_real_manuals.py`：扫 `product_manuals/*.pdf`，按文件名推断 `brand` / `category` / `model`，生成 `<file>.metadata.json` sidecar 草稿，并把 PDF 移到 `product_manuals/<category>/` 子目录（README 规定的位置）
  - 类目映射：`HR6FDFF701SW = washer (童锁出现在原 fixture)`、`BSA5221 / DHGA901NL / DHQE800BW2 = dishwasher (DH/BSA prefix)`、`W6564 = washer (ASKO W= washer)` — 这些是 best-guess，跑通后用户可校正
- **D4 评估方式 = 手写 query 集 + 双 embedder 候选并集 + 人工 review 答案**
  - 不依赖现有 fixture（那是 hashing-fixture 时期标的，与 5 份 PDF 不匹配）
  - 写 `tests/fixtures/eval/realmanuals.jsonl`（10-15 query），覆盖：
    - 故障码 query（每份 PDF 找 1-2 个真故障码）
    - 维护 query（清洁、滤芯、保养）
    - 跨章节"模糊"query（最初命题靶子："xxx 怎么办" → 多个章节并列召回）
    - 跨产品 negatives（与 cross_kb_negatives 同类型）
- **D5 实验组合 = 4 个**：
  - `vec-only` (spike_enabled=false, KNN 纯向量)
  - `wave-baseline` (spike_enabled=true, 3 readiness flag 全 off)
  - `wave-residuals` (spike_enabled=true, intrinsic_residuals_enabled=true)
  - `wave-resonance` (spike_enabled=true, cross_domain_resonance_enabled=true)
  - 不测 geodesic — Phase 4 readiness 实证它在精确 query 上扰动，需要 Phase 4.1 query-level 启发式才能用，不在本任务
- **D6 验收 = 实证报告，不强求"wave 必赢"**
  - 主要交付物是 `research/realmanuals-eval-report.md`：4 个实验组的指标 + 用户层面 query 召回案例分析
  - 如果 wave-baseline 显著 ≥ vec-only ⇒ 命题验证成功
  - 如果 wave-baseline ≈ vec-only ⇒ 在 PDF 一页一 chunk 结构下 wave 优势受限，下一步任务改 PDF 切分（不是改算法）
  - 如果 wave-baseline < vec-only ⇒ 严肃讨论是不是要回滚某些 phase（实证驱动决策）

## Requirements

### 工具

- 新增 `scripts/ingest_real_manuals.py`：
  - 扫 `product_manuals/*.pdf`（root 下散放的 5 份）
  - 推断 category，移动到 `product_manuals/<category>/<filename>.pdf`
  - 生成 sidecar `<file>.metadata.json` 草稿（manual_id / title / category / brand / language / tags），用户可校正
  - 幂等（已经分类的不重复移动）
- 新增 `scripts/diag_realmanuals_eval.py`：
  - 跑 4 配置 × `tests/fixtures/eval/realmanuals.jsonl` × siliconflow，输出指标 + delta 表 + 推荐结论
  - 复用 `build_eval_baseline._with_retry` + `_smoke_check_siliconflow`

### Fixture

- 新增 `tests/fixtures/eval/realmanuals.jsonl`（10-15 query）：
  - 用 dual-embedder 候选 + AI 起草 + 人工 review（同 Phase A 流程）
  - 答案 ground truth 用 `text_contains` 短语匹配（与现有 schema 一致），但因为 PDF 是 `Page N` header，**header 字段不能 exact match**——需要写 `header=""` 让 matcher 忽略 header
  - 实测：看下 `_matches` 是不是 header 为空就跳过

### KB build

- 命令：`python -m tagmemorag build --docs product_manuals --kb realmanuals --config <yaml>`
- 用 siliconflow embedder
- 不动 default KB

### 实验

- 4 个配置跑过同一 fixture，输出 (precision/recall/MRR/hit@k) × 4 配置 × 每 query
- 主要观测指标：`wave-baseline` vs `vec-only` 的 delta — 这是命题验证

### 文档

- 实验完成后写 `research/realmanuals-eval-report.md` 总结：
  - 实验数据 + 各组指标
  - 命题验证结论（wave 是否赢 KNN）
  - 后续工作建议（改 PDF 切分 / 调 Phase / 回滚某 phase）

## Acceptance Criteria

- [ ] `scripts/ingest_real_manuals.py` 跑通，5 份 PDF 移到 `product_manuals/<category>/` 并生成 sidecar
- [ ] `realmanuals` KB build 成功（siliconflow embedder）
- [ ] `tests/fixtures/eval/realmanuals.jsonl` 含 ≥ 10 query 真实 ground truth
- [ ] `scripts/diag_realmanuals_eval.py` 跑通 4 配置 × 全 query
- [ ] `research/realmanuals-eval-report.md` 含命题验证结论 + 数据 + 后续建议
- [ ] pytest 全绿（不引入新断言）
- [ ] hashing CI 默认 8/8 strict 绿（不影响）
- [ ] commit 含 ingest 工具 + diag 工具 + fixture + 实验报告

## Out of Scope

- PDF→Markdown 章节级 parser 升级（独立任务，根据本任务结论决定优先级）
- geodesic flag 评估（已在 wave-readiness-flags 决定 KEEP_OFF）
- 改 wave_phase1 算法或参数
- 把 realmanuals 加进 `run_eval_ci.py` 默认 CI（fixture 太大每次跑太慢，留作 informational）
- 优化 PDF parser 性能 / 改 chunk 粒度

## Definition of Done

- 实验报告完整，结论清晰（wave 赢 / 平 / 输 三种之一 + 推荐路径）
- 实验工具（ingest + diag）可复用，未来加新 manual 不用从零做
- pytest / hashing CI 不漂

## Research References

- `tests/fixtures/eval/coffee.jsonl` — Phase A 重标参考（dual-embedder review 流程）
- `scripts/relabel_eval_fixture.py` — 候选生成器，本任务可复用
- `scripts/diag_wave_readiness_flags.py` — readiness diag 模板
- `src/tagmemorag/parser.py:87` — PDF parser 现状
- `product_manuals/README.md` — sidecar 格式
