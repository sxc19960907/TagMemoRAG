# Implementation Plan — siliconflow baseline 重训

> 父文档：[prd.md](./prd.md)
> 本任务为 lightweight 任务（无独立 design.md，技术决策都在 PRD D1–D6）

## Checklist

### Stage 1：build_eval_baseline 改造

- [ ] 改 `_build_config(EMBEDDER_SILICONFLOW)` 的 `name="Qwen/Qwen3-VL-Embedding-8B"`、`dim=4096`。
- [ ] 加 smoke test fn `_smoke_check_siliconflow(cfg) -> None`：单 query embed 一次，成功就 return；失败按错误类型分别给 stderr 修复建议（API key 缺失 / 401 / model 名错 / endpoint 不通 / 通用网络错），exit 2。
- [ ] 加 `_with_retry(fn, *, max_attempts=5, base_backoff=1.0)` helper：仅捕 `EmbeddingError` + `urllib.error.URLError` + `TimeoutError`；按 `1s/2s/4s/8s/16s` sleep；5 次都失败时透传最后一次异常。
- [ ] 把 `run_eval(...)` 调用包到 `_with_retry` 里。
- [ ] 加 `--compare-with <baseline.json>` 参数：跑完 capture 后读旧 baseline，打印 hashing vs siliconflow 的 delta 表（per suite × per metric，正负号 + 4 位小数），不写到文件。
- [ ] 验证写入路径走 atomic：当前 `args.output.write_text(...)` 不是 atomic，改成 `tmp = args.output.with_suffix(args.output.suffix + ".tmp")`; `tmp.write_text(...)`; `tmp.replace(args.output)`。
- [ ] 新增最小单测 `tests/unit/test_build_eval_baseline.py`（无网络）：覆盖 `_with_retry` 三个分支（首次成功 / 重试后成功 / 5 次失败）+ delta diff 函数（hashing.json fixture mock）。

### Stage 2：run_eval_ci 改造

- [ ] 加 `--embedder hashing|siliconflow`（默认 hashing），与 `--baseline` 联动。
- [ ] 拆 `_hashing_config_yaml` 为 `_config_yaml(data_dir, *, embedder, geodesic)`，hashing 路径字节相等于现状；siliconflow 路径生成 `model.provider=http` + `model.name=Qwen/Qwen3-VL-Embedding-8B` + `model.dim=4096` + `model.api_key_env=SILICONFLOW_API_KEY` + `model.base_url=https://api.siliconflow.cn/v1` + `model.normalize=true`。
- [ ] 校验：默认 `python scripts/run_eval_ci.py` 字节等价于 master（hashing 全 8 套绿）。

### Stage 3：smoke + 跑 baseline + 落盘

- [ ] 本地 export `SILICONFLOW_API_KEY`，先跑单 query smoke：`python -c "from tagmemorag.embedder import HttpEmbedder; e = HttpEmbedder(...Qwen-VL...); print(e.encode_query('蒸汽很小').shape)"`，确认 (4096,) 且 normalize。
- [ ] smoke 通过后跑全 baseline：`python scripts/build_eval_baseline.py --embedder siliconflow --output tests/fixtures/eval/baselines/siliconflow.json --compare-with tests/fixtures/eval/baselines/hashing.json` 把 stdout delta 表存档。
- [ ] 验证 `siliconflow.json` schema 与 hashing.json 一致；`config_hash` 不同；`embedder=siliconflow`。
- [ ] `python scripts/run_eval_ci.py --baseline tests/fixtures/eval/baselines/siliconflow.json --embedder siliconflow` 全 8 套 suite 绿。

### Stage 4：文档同步

- [ ] README 加 "Two baselines" 子段：hashing = 默认 CI 门禁；siliconflow = readiness 精检；列两条命令示例 + 何时各跑哪条。
- [ ] `docs/wave-phase1-architecture.md`：在 Phase 4 段或新加 "Baselines" 段简述双轨语义。
- [ ] `.trellis/spec/backend/quality-guidelines.md` §HTTP Embedding Provider：如不冗余可补 siliconflow baseline 重训命令示例。

### Stage 5：回归 + commit

- [ ] 全量 `pytest tests/` 必须 435 + 新增测试全绿。
- [ ] `python scripts/run_eval_ci.py`（默认 hashing）继续全绿。
- [ ] `python scripts/run_eval_ci.py --baseline siliconflow.json --embedder siliconflow` 全绿。
- [ ] commit message 包含 hashing vs siliconflow delta 表（来自 Stage 3 stdout）。

## Validation

```bash
# Stage 1 (脚本测试)
.venv/bin/python -m pytest tests/unit/test_build_eval_baseline.py

# Stage 2 (CI 字节稳定)
.venv/bin/python scripts/run_eval_ci.py

# Stage 3 (smoke + capture + verify)
SILICONFLOW_API_KEY=$SILICONFLOW_API_KEY \
  .venv/bin/python scripts/build_eval_baseline.py \
    --embedder siliconflow \
    --output tests/fixtures/eval/baselines/siliconflow.json \
    --compare-with tests/fixtures/eval/baselines/hashing.json
.venv/bin/python scripts/run_eval_ci.py \
  --baseline tests/fixtures/eval/baselines/siliconflow.json \
  --embedder siliconflow

# Stage 5 (全量回归)
.venv/bin/python -m pytest tests/ -q
```

## Review Gates

- **Gate A (Stage 1 后)**：`_with_retry` 单测三分支全绿；现有 `build_eval_baseline` 行为（hashing path）未漂。
- **Gate B (Stage 2 后)**：`run_eval_ci.py` 默认 hashing path 全 8 套 suite 字节稳定。
- **Gate C (Stage 3 后)**：siliconflow.json 写入成功 + delta 表打印完整 + run_eval_ci siliconflow path 全绿。
- **Gate D (Stage 5 前)**：pytest 全量回归 + hashing baseline 字节稳定 + siliconflow baseline 全绿。

## Rollback Points

- Stage 1-2 失败：本地 git stash / revert 单个 commit。
- Stage 3 跑到一半 SIGINT 或网络断：D6(h) atomic write 保证 siliconflow.json 不留半文件，重新跑即可（每次 capture 是无状态的）。
- Stage 3 数据看起来明显异常（比如所有指标都是 0）：debug 后重跑，不进 commit；本任务范围内允许不限次数重跑。
- 极端情况：API key 失效 / Qwen-VL endpoint 永久不可用 → 任务挂起，回到 brainstorm 阶段重选 model（D5 重做）。
