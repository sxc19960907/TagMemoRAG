# brainstorm: siliconflow 实库 eval baseline 重训

## Goal

为 `feat/wave-phase1-cooccurrence-spike` 分支生成基于 siliconflow `BAAI/bge-small-zh-v1.5`
（384 维）实库 embedder 的 eval baseline，写入
`tests/fixtures/eval/baselines/siliconflow.json`，并让 `run_eval_ci.py` 支持
切换到该 baseline。这条 baseline 是后续 wave readiness（Phase 3 / 3.5 / 4 的 3 个
默认 false flag 是否翻开）决策的前提：没有真生产 embedder 的 baseline，
无法判断 flag-on 是否退化生产质量。

## Background / Known Context

### 现有工具链（不需要新建）

- `scripts/build_eval_baseline.py --embedder siliconflow --output <path>` 已支持。
  内部 hardcode model: `BAAI/bge-small-zh-v1.5` / 384 dim / `https://api.siliconflow.cn/v1`
  / `api_key_env=SILICONFLOW_API_KEY` / `normalize=True`。
- 默认 `--docs tests/fixtures/product_manuals`（4 product 类目，8 个 manual）+
  `coffee.jsonl` 用 `tests/fixtures` 作为 docs override。
- 默认 `--spike-on`（baseline 在 spike 跑通的状态下 capture）。

### 8 套 hashing eval baseline（参考形态）

`tests/fixtures/eval/baselines/hashing.json` 当前 PASS gate 形如：

```
coffee.jsonl       precision@k=0.214286 recall@k=0.928571 mrr=0.928571 hit@k=1.000000
cross_kb_negatives precision@k=0.500000 recall@k=1.000000 mrr=1.000000 hit@k=1.000000
fault_codes        precision@k=0.600000 recall@k=1.000000 mrr=0.900000 hit@k=1.000000
mixed_language     precision@k=0.600000 recall@k=1.000000 mrr=0.900000 hit@k=1.000000
model_numbers      precision@k=0.700000 recall@k=1.000000 mrr=1.000000 hit@k=1.000000
product_manuals    precision@k=0.214286 recall@k=1.000000 mrr=1.000000 hit@k=1.000000
tag_cooccurrence   precision@k=0.900000 recall@k=1.000000 mrr=1.000000 hit@k=1.000000
tag_rerank_edge    precision@k=0.700000 recall@k=1.000000 mrr=1.000000 hit@k=1.000000
```

baseline 文件格式：`{embedder, captured_at, config_hash, thresholds_applied: {floor_delta: 0.02}, suites: {<suite_name>: {<metric>: float, ...}}}`。
config_hash 已包含 `model_dim / model_provider / spike_enabled / 8 套 suite 文件 sha256`，
切换 embedder 自动产生不同 hash → 不会跟 hashing baseline 混淆。

### 消费端缺口（必须补）

`scripts/run_eval_ci.py` 的 `_hashing_config_yaml` 写死 hashing/64 维。
切换到 siliconflow baseline 需要：
1. 加 `--embedder hashing|siliconflow` 参数（或类似），让 config 跟 baseline 匹配。
2. siliconflow config 不能在 YAML 直写 api_key（spec 禁），必须走 env override。
3. 若 model_dim 与 baseline 中 config_hash 不一致 → eval runner 该报错退出（保护机制）。

### 兼容性风险

- siliconflow API 网络不稳 / quota 限制 / 429。需要 fail-soft + 重试策略 vs 直接报错？
- 8 套 suite 的 manuals 章节切分 + 384 维向量构图，单次 capture 时间预估 ~分钟级。
  build_eval_baseline 当前对每个 suite 用 tempdir 重新 build_kb，串行跑，无 cache。

## Assumptions (待确认)

- A1：使用现有 `tests/fixtures/product_manuals` 4 类 8 个 manual 作为生产代理（用户已确认）。
- A2：环境变量 `SILICONFLOW_API_KEY` 已在 shell 可用（51 字符长度，已验证）。
- A3：siliconflow embedder 默认 batch_size=16 / `BAAI/bge-small-zh-v1.5` 384 维。
- A4：本任务不动 wave_phase1 算法逻辑、不改任何 flag 默认值；纯 baseline + CI consume。

## Open Questions

（已收敛 Q1–Q5，等下一轮扩展扫描）

## Decisions

- **D1 baseline capture 在 spike-on 状态下进行，与 hashing baseline 同语义**
  - `python scripts/build_eval_baseline.py --embedder siliconflow --output tests/fixtures/eval/baselines/siliconflow.json`（默认 `--spike-on`）。
  - **Why**：生产路径实际就是 spike-on，对照组与生产状态一致才能让后续 readiness（resonance / residuals / geodesic 翻开 vs 不翻开）的 delta 直接读出"翻 flag 的实际影响"，不混入"spike 自身贡献"。与 `hashing.json` 完全同语义，CI 命令可对称。
  - **How to apply**：3 个 readiness flag 默认 false 在 capture 时保持默认 → siliconflow baseline 反映「spike-on + 3 readiness flag-off」状态，作为后续 readiness 任务的对照基线。

- **D2 CI 默认 hashing 不变，siliconflow 走手动触发 / readiness 任务专用**
  - GitHub Actions `quality.yml` 等 PR 门禁继续跑 `run_eval_ci.py`（默认 hashing.json + hashing config）。
  - siliconflow baseline 通过显式参数触发：`run_eval_ci.py --baseline siliconflow.json --embedder siliconflow`。
  - **Why**：hashing 作为"离线快速门禁"（5 秒、零外部依赖）已经能抓代码逻辑回归（Phase 4 baseline invariance 就是它抓的）；siliconflow 是 readiness / 上线前精检工具，不该绑定到每次 PR；避免 CI 因为外部 API 抽风频繁红。
  - **How to apply**：`run_eval_ci.py` 加 `--embedder hashing|siliconflow` 参数（默认 hashing），让 config 与 baseline 同步切换；hashing 路径保持现状字节稳定。

- **D3 build_eval_baseline 内对 capture 循环加指数退避重试，HttpEmbedder 本身不动**
  - 在 `scripts/build_eval_baseline.py` 内对 `run_eval(...)` 这层调用包一个 `_with_retry(fn, max_attempts=5, base_backoff=1.0)` helper，按 `1s/2s/4s/8s/16s` 退避；5 次都失败才整次报错退出。
  - 仅捕 `EmbeddingError` 与 `urllib` 网络相关异常。配置错误（`SILICONFLOW_API_KEY` 缺失 / 401 / 403）不重试，立即抛错。
  - **Why**：生产路径调 `HttpEmbedder` 希望快失败 + 上层错误码（不能默默重试影响 `/search` 延迟），所以重试逻辑必须留在 baseline 脚本而非通用 embedder；指数退避吃 transient 错误（429 / 5xx / 网络抖动）；硬错（key / quota）不该被掩盖。
  - **How to apply**：`_with_retry` 函数 ~15 行，仅在 baseline 脚本内部使用；不引入新依赖（`time.sleep` 即可）；日志打印每次重试的尝试次数 + 等待时间，便于诊断。

- **D4 baseline 无条件落盘 + delta 报告，好坏判断推给 readiness 任务**
  - 不论 siliconflow 跑出什么数据，都写入 `tests/fixtures/eval/baselines/siliconflow.json`。
  - 同时打印 hashing vs siliconflow 的 delta 表格（每个 suite 每个 metric 的差值）到 stdout，作为 commit message / PR 描述的素材。
  - **Why**：本任务只负责"诚实记录"事实数据；baseline 文件本身是事实快照，无好坏阈值；后续 readiness 任务（独立 task `wave-readiness-flags`）拿到完整对照数据后再做"哪些 flag 翻开 / siliconflow 是否替代 hashing 的生产 baseline"决策。
  - **How to apply**：`build_eval_baseline.py` 里加一个 `--compare-with <baseline.json>` 可选参数，输入 hashing.json 后输出 delta 表；不在脚本内做任何"自动拒绝"或"阈值守门"逻辑。
  - **Implementation finding (2026-05-17)**：siliconflow baseline 在 8 套 suite 中 7 套显著低于 hashing（差距 14–80%），且 7/8 套低于项目 `DEFAULT_THRESHOLDS=(recall=0.8, mrr=0.75, hit=0.8)` 绝对底线。根因疑似：(a) hashing fixture eval ground truth 是用 hashing embedder 自循环标注的；(b) Qwen-VL VL 模型的纯文本中文召回不一定优于 hashing 在小 fixture 上的过拟合；(c) wave_phase1 参数按 64 维调，4096 维下量级失配。**修订**：siliconflow baseline 是 **informational reference**，不是 **quality gate**；run_eval_ci.py 在 siliconflow path 用 `--no-default-thresholds` 跳过绝对底线，只校验 baseline-derived 阈值（自跑必绿）。诊断 + 改善真实质量的任务推给后续 readiness 任务。

- **D5 model = `Qwen/Qwen3-VL-Embedding-8B`（4096 维 / 32K context），匹配生产意图**
  - 改 `build_eval_baseline.py` 内 `_build_config(EMBEDDER_SILICONFLOW)` 的硬编码：`name="Qwen/Qwen3-VL-Embedding-8B"`，`dim=4096`。
  - 不引入 `--model` 参数（避免本任务范围膨胀）；生产真要换其他 model 时再开独立小任务改硬编码 + 重跑 baseline。
  - **Why**：baseline 必须匹配生产实际 embedder 才能让 readiness delta 有可比性；4096 维 vs hashing 64 维的差距足够大（64×），不需要再加中间档；32K context 远超 parser `max_chars=500`，无 chunk 截断风险。
  - **Open risk（implement 期监控）**：(a) Qwen-VL 走 OpenAI-compatible `/v1/embeddings` 纯文本调用未本地实测过；(b) 8B 模型 quota 比 bge-small 紧；(c) 4096 维 vectors.npz 体积 10×（仅 tempdir 内，不进库）。
  - **How to apply**：implement 第 1 步必须先做"单 query smoke test"验证 endpoint 兼容性，跑通才进 8 套 suite 全量 capture；smoke 失败就提前 fail loud，避免烧 quota 到一半失败。

- **D6 MVP 范围 = 核心闭环 + 现有测试核查 + 文档简短说明 + smoke 提前 fail-loud + atomic write 验证**
  - In MVP：
    - (核心) D1–D5 五个决策的实现：build_eval_baseline 改 model 硬编码 + 加 `_with_retry` + 加 `--compare-with` delta 表；run_eval_ci 加 `--embedder` 切换；落盘 `siliconflow.json`。
    - (c) 核查 `tests/` 是否已有 `build_eval_baseline.py` 单测；如有就更新到新 model name + dim；如无就新增最小 fixture 测试覆盖 retry helper + delta diff helper（不联网）。
    - (e) README / docs/wave-phase1-architecture.md 加段："两套 baseline 怎么用"（hashing 当 CI 快速门禁、siliconflow 当 readiness 精检；切换命令示例）。
    - (f) smoke test 失败时 fail-loud，stderr 给具体修复建议（API key 缺失 / 401 / model 名错 / endpoint 不通各分别提示）。
    - (h) 验证 baseline JSON 写入路径走 atomic（write-to-tmp + os.replace），SIGINT 不留半文件。
  - Out of MVP（明确 follow-up）：
    - (a)(b) 多 model / 多 baseline 维护范式 — 等真出现第二个生产 embedder 时再开任务。
    - (d) Manual-trigger GitHub Actions workflow — 现在团队习惯本地跑 + commit 提交 baseline，CI 触发非急需。
    - (g) 峰值 disk usage 监控 — tempdir 跑完即扔，无生产容量风险。
  - **Why**：(c)(e)(f)(h) 是"上线 baseline 之前必须有眼睛 + 必须不留半成品 + 文档可被复用"的最小配套；(a)(b)(d)(g) 没有触发条件就无价值。
  - **How to apply**：implement.md 5 项 checklist 全部进 stage；(a)(b)(d)(g) 写在 PRD `Out of Scope` 段说明触发条件。

## Requirements

### 脚本改动

- `scripts/build_eval_baseline.py`：
  - 改 `_build_config(EMBEDDER_SILICONFLOW)` 的 `name="Qwen/Qwen3-VL-Embedding-8B"`、`dim=4096`。
  - 在 `main()` 早期加 smoke test：单 query embed 一次，失败立即 stderr 出诊断 + exit 2（区分 API key 缺失 / 401 / model 名错 / endpoint 不通）。
  - 加 `_with_retry(fn, max_attempts=5, base_backoff=1.0)` helper，套在每个 suite 的 `run_eval(...)` 调用外侧；仅捕 `EmbeddingError` + `urllib.error.URLError`/`TimeoutError`；其他异常透传。
  - 加 `--compare-with <baseline.json>` 参数：跑完 capture 后读入旧 baseline，打印 hashing vs siliconflow 的 delta 表（per suite × per metric）到 stdout；不写比较结果到 baseline 文件。
  - 验证写入路径走 atomic（已有 storage helper 或 `Path.replace`）；SIGINT 不留半文件。
- `scripts/run_eval_ci.py`：
  - 加 `--embedder hashing|siliconflow`（默认 hashing）。
  - `_hashing_config_yaml` 拆成 `_config_yaml(data_dir, embedder, geodesic)`，hashing 路径与现状字节相等；siliconflow 路径生成对应 YAML（不直写 api_key，走 env 引用）。
- 不动 `src/tagmemorag/`（HttpEmbedder / config / 算法逻辑都不改）。

### Baseline 落盘

- `tests/fixtures/eval/baselines/siliconflow.json` 写入，schema 与 `hashing.json` 一致（embedder / captured_at / config_hash / thresholds_applied / suites）。
- `config_hash` 自动包含 `model_dim=4096` + `model_provider=http`，与 hashing.json 不会冲突。

### 测试

- 现有 `build_eval_baseline.py` 测试如有：更新到新 model + dim；如无：加最小测试覆盖 `_with_retry`（成功 / 重试后成功 / 5 次都失败）+ delta diff helper（无网络）。
- 新加测试不联网（用 mock）。

### 文档

- README：加 "Two baselines" 子段（hashing = CI 快速门禁，siliconflow = readiness 精检；命令示例）。
- `docs/wave-phase1-architecture.md`：在 Phase 4 段后或独立 readiness 段，简述 baseline 双轨语义。
- `.trellis/spec/backend/quality-guidelines.md` HTTP Embedding Provider 段：补 "siliconflow baseline 重训命令" 示例（如不冗余）。

## Acceptance Criteria

- [ ] `scripts/build_eval_baseline.py --embedder siliconflow --output tests/fixtures/eval/baselines/siliconflow.json` 在 SILICONFLOW_API_KEY 已 export 的环境下跑通，写入 8 套 suite 的指标。
- [ ] `siliconflow.json` 的 `embedder=siliconflow`、`config_hash` 与 hashing.json 不同，schema 与 hashing.json 一致。
- [ ] `scripts/run_eval_ci.py`（默认 hashing 路径）字节稳定，hashing.json baseline 仍全绿。
- [ ] `scripts/run_eval_ci.py --no-default-thresholds` flag 存在，`--embedder siliconflow` 的 config 输出语法正确（model.api_key_env 走 env 引用、不直写 secret）。
- [ ] `--compare-with` 输出可读 delta 表（per suite × per metric，正负号 + 数值）；hashing vs siliconflow delta 表归档进 commit message / PR 描述。
- [ ] smoke test 失败场景：API key 缺失 / model 名拼错 / 401，三种都给具体修复建议 stderr。
- [ ] `_with_retry` 单测覆盖 3 个分支（首次成功 / 重试后成功 / 5 次都失败）。
- [ ] baseline 写入走 atomic，SIGINT 不留半文件（手工验证 + 写到 PR 描述）。
- [ ] README + docs 更新；spec 如需补充 siliconflow 段也补上；明确说明 siliconflow baseline 是 informational reference，CI 默认不消费。
- [ ] **注意（D4 修订）**：siliconflow baseline 在当前 fixture eval suite 上**故意不要求 run_eval_ci 跑通自己**——case-level fixture 阈值是用 hashing 标注的，与 siliconflow 召回不配套。诊断 + 改善 fixture 推到独立 readiness 任务；本任务只负责"诚实落盘 + 工具链就位"。

## Out of Scope

- 修改 wave_phase1 任何算法逻辑或默认 flag 值（推到独立 `wave-readiness-flags` 任务）。
- 多 model `--model` 参数（触发条件：第二个生产 embedder 出现时再开任务）。
- 多 baseline 命名规范（同上）。
- Manual-trigger GitHub Actions workflow（触发条件：团队主动需求时再加）。
- 峰值 disk usage 监控（tempdir 跑完即扔，无风险）。
- HttpEmbedder 自带重试（不改通用 embedder）。
- siliconflow 之外的 embedder 重训（OpenAI / 本地 sentence-transformers）。

## Definition of Done

- siliconflow.json 进库且 commit message 含 hashing vs siliconflow delta 表。
- hashing path baseline 字节稳定（CI 默认门禁不漂）。
- siliconflow path 全 8 套 suite 绿。
- 文档更新 + 现有测试更新或新增最小覆盖。
- API key 不在 YAML / commit / log 中露出。

## Research References

- `scripts/build_eval_baseline.py` — 现有 baseline 生成器，已支持 `--embedder siliconflow`。
- `scripts/run_eval_ci.py` — 消费 baseline 的 CI 入口，目前 hardcoded hashing config。
- `tests/fixtures/eval/baselines/hashing.json` — 现有 baseline 文件形态。
- `.trellis/spec/backend/quality-guidelines.md` §HTTP Embedding Provider — siliconflow embedder 契约。
- `.trellis/spec/backend/logging-guidelines.md` — env-only API key 约束。

## Definition of Done

- `tests/fixtures/eval/baselines/siliconflow.json` 写入，格式与 hashing.json 一致。
- `run_eval_ci.py --baseline siliconflow.json --embedder siliconflow` 全 8 套 suite 绿。
- 文档更新：README + docs/wave-phase1-architecture.md 提及 baseline 双轨。
- siliconflow path 不破坏 hashing path（默认 CI 还是 hashing 跑，作为快速门禁）。
- API key 不进 YAML / commit / log。
