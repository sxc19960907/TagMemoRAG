# brainstorm: M3 质量回归（Eval 框架 + CI 门禁）

## Goal

在 M0-M2 的功能、运维、安全和多 KB 能力之上，补齐**检索质量回归护栏**：提供可版本化的标注集格式、本地离线 eval runner、核心检索指标（precision@k / recall@k / MRR）和 CI 门禁。完成后，任何改动核心 parser、graph、embedding、wave search、anchor 或配置默认值的 PR，都能自动发现检索质量退化。

## Background / Known Context

- 路线图定义：**M3 质量回归** = Eval 框架（标注集 + precision@k/recall@k/MRR）/ CI 回归门禁 / 错误码枚举，交付物是“退化自动告警”。
- M0 已实现 Markdown/TXT parser、graph builder、anchor、JSON+NPZ storage、CLI build/search、FastAPI search/rebuild。
- M1 已实现结构化日志、health/ready、Docker、env config、graceful shutdown 和模型 warm-up。
- M2 已完成 API key、限流、多 KB、查询缓存；M3 的 eval 需要能指定 `kb_name`，但默认只跑离线单进程，不依赖 HTTP 服务。
- 现有测试里 `tests/e2e/test_coffee.py` 只断言“蒸汽很小”能召回若干关键词，尚不是可扩展的标注集和指标体系。
- 现有测试使用 `HashingEmbedder`，不需要下载 HuggingFace 模型；M3 CI 也应默认使用 deterministic/offline embedder。
- 现有 CLI 有 `build`、`search`、`serve`、`auth generate-key`，没有 `eval` 子命令。
- 当前依赖里已有 `numpy`、`pydantic`、`pyyaml`、`pytest`，M3 可先不引入 pandas/sklearn 等新依赖。

## Assumptions (temporary)

- M3 的首要目标是**回归检测**，不是构建大型人工评测平台。
- 第一版标注集规模小：每个 fixture KB 10-100 条 query，CI 可在数秒到几十秒内完成。
- CI 默认用 `HashingEmbedder` 保证稳定和离线；真实模型质量评估可作为手动 profile。
- 标注答案以“期望命中文档块”表达，而不是要求生成式答案一致。
- 指标门禁以聚合阈值为主，单 query 失败明细必须输出，方便定位。
- 默认 eval 从 docs 构建时必须隔离 storage，避免污染或依赖现有 `data/{kb_name}`；只有显式 `--reuse-built-kb` 才读取已有 KB。

## Decision (ADR-lite)

### Decision: Eval runner 默认离线运行，不走 FastAPI

**Context**：M3 可以复用 HTTP `/search`，也可以直接调用 parser/build/search 内部函数。CI 中 HTTP 服务会引入端口、鉴权、缓存、限流和启动时序噪音。

**Decision**：
- M3 默认实现 `tagmemorag eval run` CLI，直接在进程内执行：
  1. 加载 config
  2. 使用指定 embedder 构建临时 KB 或加载已有 KB
  3. 对标注 query 执行 `wave_search`
  4. 计算指标并输出 JSON report
- HTTP eval 留到 post-v1 或 M4 观测联调，不作为 M3 验收路径。

**Rationale**：
- 回归门禁要稳定、快、可重复；进程内 eval 最少变量。
- 可以直接复用现有 `build_kb / load_kb / wave_search`，不绕 API 鉴权和限流。
- 对 parser/graph/search 的核心退化更敏感。

**Consequences**：
- 新增 CLI 子命令 `eval run`。
- 新增 eval 模块时不要依赖 FastAPI app state。
- 从 docs 构建的默认 eval 必须使用临时 `storage.data_dir`；不得读写默认生产/开发 `data/{kb_name}`。
- E2E 测试覆盖 CLI 输出和阈值失败退出码。

### Decision: 标注集格式 = JSONL，query 级 expectation 显式列出

**Context**：标注集需要适合 code review diff、便于追加、能表达多个相关答案和 hard negative。

**Decision**：
- 默认标注集文件使用 JSONL，每行一个 query case。
- 最小字段：
  - `id`: 稳定 case id
  - `kb_name`: 知识库名，默认 `default`
  - `query`: 用户问题
  - `relevant`: 期望相关块列表
- `relevant` 中每个 item 支持：
  - `id`（可选；用于 report 定位，默认可生成 `<case_id>#<index>`）
  - `source_file`
  - `header`
  - `anchor_key`
  - `text_contains`
  - `weight`（默认 1.0，M3 指标先按 binary relevance 计算，weight 预留）
- 可选字段：
  - `tags`
  - `notes`
  - `top_k_override`
  - `min_precision_at_k`
  - `min_recall_at_k`
  - `min_mrr`
  - `min_hit_at_k`

**Rationale**：
- JSONL 适合大文件逐行 diff 和流式读取。
- `source_file + header/text_contains` 能在 anchor_key 变化时保持可读性。
- query 级阈值预留给关键业务问题。

**Consequences**：
- 新增 `eval/fixtures/coffee/eval.jsonl` 或 `tests/fixtures/eval/coffee.jsonl`。
- 新增 loader 校验：缺字段、重复 id、空 relevant 都应报结构化错误。
- README 增加标注格式示例。

### Decision: M3 指标 = precision@k / recall@k / MRR，另输出 hit@k

**Context**：路线图明确 precision@k 和 MRR；M0 PRD 的 NFR 写过 precision@5 ≥ 0.8 / MRR ≥ 0.75。为了定位问题，还需要直观的 hit rate。

**Decision**：
- 实现 query-level 和 aggregate-level：
  - `precision_at_k`
  - `recall_at_k`
  - `mrr`
  - `hit_at_k`（辅助展示，不作为首要路线图指标）
- 默认 `k=5`，可通过 CLI 和 eval config 覆盖。
- 默认门禁阈值：
  - `min_recall_at_k: 0.8`
  - `min_mrr: 0.75`
  - `min_hit_at_k: 0.8`
- 默认 report 仍输出 `precision_at_k`，但第一版不把它作为默认 CI gate。小型标注集通常每个 query 只有 1 个 relevant；在 `top_k=5` 时，即使命中第 1 名，标准 `precision@5` 也只有 `0.2`，不适合作为默认硬门槛。

**Rationale**：
- precision@k 控制 top results 噪音，recall@k 控制答案覆盖，MRR 控制第一个正确答案的位置。
- hit@k 对小标注集更易读，便于人肉排查。
- M3 保持标准 precision 定义，不为小 fixture 改写公式；等标注集更完整后再决定是否把 precision 加入默认 CI 门禁。

**Consequences**：
- JSON report 必须包含 summary 和 per-case 明细。
- 阈值失败时 CLI 退出码为 1；通过时为 0。
- 浮点比较要固定精度输出，避免 CI 文本抖动。

### Decision: CI 只跑 deterministic eval，真实模型 eval 手动运行

**Context**：本项目默认模型是 `BAAI/bge-small-zh-v1.5`，真实模型 eval 更接近生产，但 CI 下载和推理成本高，且可能被网络影响。

**Decision**：
- CI 门禁默认使用 `model.provider=hashing` 和小型 fixture。
- 手动命令支持真实模型或 HTTP embedding profile，但不进入默认 CI gate。
- M3 不要求新增 GitHub Actions，若仓库已有 CI 则接入；没有 CI 时至少提供本地 gate 命令和文档。

**Rationale**：
- 回归测试首先要稳定。
- 真实模型质量评估适合发布前或夜间任务，M4/后续再接入监控和定时报告。

**Consequences**：
- 新增 `tests/eval` 或 `tests/e2e` 覆盖 deterministic eval。
- README 的测试章节加 `uv run tagmemorag eval run ...` 示例。

## Requirements

### 1. Eval 数据格式

- 能读取 JSONL 标注集。
- 能校验 case id 唯一、query 非空、relevant 非空。
- 支持按 `kb_name` 分组运行。
- 支持 `source_file/header/text_contains/anchor_key` 组合匹配结果。
- 无法匹配标注引用时报告清晰错误，不能静默跳过。

### 2. Eval 执行器

- 提供 Python API，例如 `run_eval(config, suite_path, docs_path, ...) -> EvalReport`。
- 提供 CLI：`tagmemorag eval run --suite <path> --docs <path> --config <path> --output <path> --top-k 5`。
- 支持 `--reuse-built-kb` 或等价模式，允许直接评测已有 KB。
- 默认 CI 路径使用 `HashingEmbedder`，不下载模型。
- 输出 JSON report，包含 summary、per-case、thresholds、config snapshot 关键字段。

### 3. 指标和门禁

- 计算 `precision_at_k / recall_at_k / mrr / hit_at_k`。
- 支持 suite-level 默认阈值和 case-level 覆盖阈值。
- case-level 阈值是额外约束；suite-level 阈值仍应用于 aggregate summary。
- 任何门禁失败时 CLI 返回非零退出码。
- report 中列出失败 case 的 query、expected、actual top-k、失败指标。

### 4. 测试和文档

- 为 metric 计算写纯单元测试。
- 为 JSONL loader 写结构校验测试。
- 为 CLI gate 写通过和失败两个路径测试。
- 保留现有 M0-M2 测试全部通过。
- README 增加“Quality Eval”章节，说明如何新增标注、运行 eval、解读 report。

## Acceptance Criteria

- [ ] `uv run pytest tests/ -v` 全绿。
- [ ] `tagmemorag eval run` 能在 coffee fixture 上生成 JSON report。
- [ ] report 包含 suite summary 和每个 query 的 top-k 结果、expected match、metrics。
- [ ] 当阈值设置高于实际结果时，CLI 退出码为 1，并输出失败明细。
- [ ] 默认 eval gate 使用 offline deterministic embedder，不需要网络。
- [ ] 默认从 docs 构建的 eval 使用临时 storage，不污染现有 `data/{kb_name}`。
- [ ] README 记录标注集格式和本地/CI gate 命令。

## Definition of Done

- PRD、design、implement 文档完成并经确认。
- 新增/更新测试覆盖 loader、metrics、runner、CLI gate。
- Lint/typecheck/test 或项目等价验证通过。
- 对 M0-M2 行为无破坏：build/search/API/auth/rate-limit/cache 测试保持绿。
- 若新增配置字段，配置默认值向后兼容。
- M3 不引入重型依赖，除非有明确收益和文档说明。

## Out of Scope (explicit)

- 人工标注 UI / Web dashboard。
- LLM-as-judge 或生成式答案评分。
- 大规模生产语料全量评测。
- 定时/夜间 eval 报告。
- Prometheus metrics / OTel traces（M4）。
- HTTP API eval 模式。
- 真实模型 eval 作为默认 CI 必跑项。

## Research References

- Existing roadmap: `.trellis/tasks/archive/2026-05/05-10-wave-rag-implementation/prd.md`
- Existing M2 scope: `.trellis/tasks/05-12-m2-security-multikb-cache/prd.md`
- Existing coffee retrieval smoke test: `tests/e2e/test_coffee.py`
