# implement.md — M1 实施 checklist

> 父文档：[prd.md](./prd.md) / [design.md](./design.md)
> 原则：自底向上，按 Phase 串行。每个 Phase 结束跑一次 `pytest`。

---

## Phase A — 依赖 & 配置 env 化（~0.5 天）

- [ ] **A1** `pyproject.toml` 加依赖
  - `structlog>=24.1`
  - `pydantic-settings>=2.2`
- [ ] **A2** `uv lock` 重生成 `uv.lock`
- [ ] **A3** `src/tagmemorag/config.py` 改造
  - `from pydantic_settings import BaseSettings, SettingsConfigDict`
  - `Settings(BaseSettings)` + `model_config = SettingsConfigDict(env_prefix="TAGMEMORAG__", env_nested_delimiter="__", env_file=".env", extra="ignore")`
  - 新增 `ServerConfig` (`host/port/shutdown_timeout_seconds`)
  - 新增 `LoggingConfig` (`level/format`)
  - `Settings` 加 `server: ServerConfig` + `logging: LoggingConfig`
  - `load_config(path)` 保持签名，内部合并 YAML → Settings 构造时 env 覆盖
- [ ] **A4** `config.yaml` 加 `server:` 和 `logging:` 段（示例 + 注释）
- [ ] **A5** `.env.example` 新文件，列常用覆盖
- [ ] **A6** `tests/unit/test_config_env.py` 新建
  - `test_env_overrides_yaml`：设 `TAGMEMORAG__SERVER__PORT=9000` → `load_config` 得到 `cfg.server.port == 9000`
  - `test_env_overrides_defaults`：无 YAML 文件，纯 env → 覆盖生效
  - `test_nested_env_delimiter`：`TAGMEMORAG__MODEL__NAME=foo` → `cfg.model.name == "foo"`
  - `test_yaml_fallback`：无 env → yaml 值生效

**验证**：`uv run pytest tests/unit/test_config_env.py tests/ -v`（M0 23 个 + M1 4 个 = 27 条全绿）

---

## Phase B — 结构化日志（~1 天）

- [ ] **B1** `src/tagmemorag/logging_setup.py` 新文件
  - `configure_logging(level: str, format: str)` 函数（见 design §3.1）
  - structlog processors 顺序：`merge_contextvars → add_log_level → TimeStamper(iso, utc) → StackInfoRenderer → format_exc_info → JSONRenderer/ConsoleRenderer`
  - 桥接 uvicorn / uvicorn.access / uvicorn.error / fastapi 四个 logger
- [ ] **B2** `src/tagmemorag/cli.py` 的 `serve` / `build` / `search` 入口前调用 `configure_logging(cfg.logging.level, cfg.logging.format)`
- [ ] **B2a** `serve` 默认使用 `cfg.server.host/cfg.server.port`；`--host/--port` 仅在显式传入时覆盖配置。Docker CMD 不应硬编码 host/port。
- [ ] **B3** `src/tagmemorag/api.py` 加 trace_id 中间件（见 design §3.2）
  - `@app.middleware("http")` 注入 `trace_id / path / method` 到 contextvars
  - 响应头 `X-Trace-Id`
- [ ] **B4** 把 M0 已有的关键点改为 structlog 事件（见 design §3.3 清单）
  - `api.search`: `logger.info("search", query_len=..., top_k=..., result_count=..., latency_ms=..., build_id=...)`
  - `state.start_rebuild`: `rebuild_started`
  - `state._rebuild_worker`: `rebuild_done` / `rebuild_failed`
  - `anchor.add / delete`: `anchor_created / anchor_deleted`
  - 全局 exception handler: `request_error`
- [ ] **B5** 测试 `tests/unit/test_logging.py`
  - `test_configure_logging_json_format`：捕获 stdout，断言 JSON 可解析且含 `timestamp / level / event`
  - `test_contextvars_propagate`：bind `trace_id` → 后续 log 事件里出现
  - `test_uvicorn_bridge`：uvicorn logger 输出也走 structlog
- [ ] **B6** 测试 `tests/unit/test_api_trace.py`
  - `test_trace_id_generated_when_header_absent`
  - `test_trace_id_respected_when_header_present`
  - `test_response_header_contains_trace_id`

**验证**：`uv run pytest tests/ -v`（加上 B 的 ~6 条 → ~33 条全绿）

---

## Phase C — AppState 扩展 + 健康探针（~0.5 天）

- [ ] **C1** `src/tagmemorag/state.py` `AppState` 新增字段
  - `embedder_ready: bool = False`
  - `is_shutting_down: bool = False`
  - `mark_embedder_ready()` / `begin_shutdown()` 方法（thread-safe，用 `_lock`）
- [ ] **C2** `start_rebuild` 加前置检查：`is_shutting_down` → raise `ServiceError(SHUTTING_DOWN, ...)`
- [ ] **C3** `src/tagmemorag/errors.py` 加 `ErrorCode.SHUTTING_DOWN = "SHUTTING_DOWN"`
- [ ] **C4** `src/tagmemorag/api.py` 加 `_status_for` 映射：`SHUTTING_DOWN → 503`
- [ ] **C5** `src/tagmemorag/api.py` 加 `/health` / `/ready` 端点（见 design §4.1）
  - `PlainTextResponse`
  - `include_in_schema=False`
- [ ] **C6** `tests/unit/test_health.py`
  - `test_health_always_ok`
  - `test_ready_503_when_embedder_not_ready`
  - `test_ready_503_when_kb_not_loaded`
  - `test_ready_503_when_shutting_down`
  - `test_ready_200_when_all_ready`
  - `test_ready_does_not_use_service_error_format`（断言 text/plain）

**验证**：`uv run pytest tests/ -v`（加上 C 的 ~6 条）

---

## Phase D — Lifespan startup / shutdown 改造（~1 天）

- [ ] **D1** `src/tagmemorag/api.py` 的 `lifespan` 按 design §5.1 重写 startup
  - `configure_logging(...)`（如果 serve 入口没调过，此处兜底）
  - 初始化 embedder（M0 已有，保留懒化）
  - warm-up encode `"warmup"` + 测耗时 + 打日志
  - warm-up 失败 → `structlog.error` + `sys.exit(1)`
  - `mark_embedder_ready()`
  - load_kb（M0 已有）
  - 最后打 `service_ready` 日志
- [ ] **D2** lifespan shutdown 段（design §5.2）
  - `begin_shutdown()`
  - `await asyncio.to_thread(app_state._rebuild_lock.acquire)` + `release()`
  - 日志 `rebuild_drained` / `shutdown_complete`
- [ ] **D3** `tests/unit/test_shutdown.py`
  - `test_shutdown_waits_for_rebuild`：起 BlockingEmbedder 的 rebuild → lifespan shutdown 触发 → 释放 blocker → shutdown 正常完成，rebuild status=done
  - `test_rebuild_rejected_after_begin_shutdown`：`begin_shutdown()` → `/rebuild` → 503 `SHUTTING_DOWN`
  - `test_lifespan_startup_exits_on_warmup_failure`：mock embedder 的 encode_query 抛异常 → lifespan startup 抛 SystemExit

**验证**：`uv run pytest tests/ -v`（加上 D 的 ~3 条 → ~42 条全绿）

---

## Phase E — Docker 化（~1 天）

- [ ] **E1** `Dockerfile`（见 design §6.1 + §6.2）
  - Stage 1 builder：slim + uv + `uv sync --frozen --no-dev` + 模型预下载
  - Stage 2 runtime：slim + `app` 用户 + COPY venv/hf_cache/src + env vars + CMD
- [ ] **E2** `.dockerignore`（见 design §6.4）
- [ ] **E3** `docker-compose.yml`（见 design §6.3）
  - volumes: `./data:/app/data`
  - healthcheck 用 `/health`（Compose 只做进程健康；K8s readiness 用 `/ready`）
  - `stop_grace_period: 60s`
  - `read_only: true` + `tmpfs: /tmp`
- [ ] **E4** 构建与运行
  ```bash
  docker build -t tagmemorag:m1 .
  docker images tagmemorag:m1 --format "{{.Size}}"   # 应 < 1GB
  docker-compose up -d
  curl http://127.0.0.1:8000/health    # 200
  curl http://127.0.0.1:8000/ready     # 起先 503（无 KB），后续加载或 rebuild 一次 → 200
  ```
- [ ] **E5**（可选）`tests/integration/test_docker.py`：用 subprocess 调 `docker build` + `docker run` + curl。CI 慢，默认 skip，加 `@pytest.mark.docker`

---

## Phase F — 文档 & 收尾（~0.5 天）

- [ ] **F1** `README.md` 加章节（见 design §8）
  - Docker 部署
  - Environment Variables 表
  - K8s probe 配置示例
- [ ] **F2** `AGENTS.md` 同步更新（如果项目有 agent onboarding 文档）
- [ ] **F3** 回归跑 `uv run pytest tests/ -v` 全绿
- [ ] **F4** 真实模型 smoke test
  ```bash
  docker-compose up -d
  # Use a mounted docs directory or an image-bundled sample docs directory.
  curl -X POST http://127.0.0.1:8000/rebuild -d '{"docs_dir":"/app/sample-docs"}' -H "Content-Type: application/json"
  # poll rebuild status
  curl -X POST http://127.0.0.1:8000/search -d '{"question":"蒸汽很小"}' -H "Content-Type: application/json"
  ```
- [ ] **F5** commit + 归档任务

---

## 验证命令清单

```bash
# 单元测试
uv run pytest tests/unit/ -v

# 全部（含 E2E）
uv run pytest tests/ -v

# env override 快速检查
TAGMEMORAG__SERVER__PORT=9000 uv run python -c "from tagmemorag.config import load_config; print(load_config().server.port)"

# 日志格式检查
TAGMEMORAG__LOGGING__FORMAT=json uv run python -m tagmemorag search "test" 2>&1 | head -5

# Docker
docker build -t tagmemorag:m1 .
docker-compose up -d
curl -v http://127.0.0.1:8000/health
curl -v http://127.0.0.1:8000/ready
```

---

## Review Gates

- **Gate 1（Phase A 完成）**：env 覆盖真能生效？手工设 `TAGMEMORAG__SERVER__PORT=9999` 验证
- **Gate 2（Phase B 完成）**：日志输出是 JSON 且含 trace_id？`curl /search`，观察 stdout
- **Gate 3（Phase C 完成）**：`/ready` 状态正确切换？手工造 `embedder_ready=False` 等状态
- **Gate 4（Phase D 完成）**：shutdown 流程真能等 rebuild？`test_shutdown_waits_for_rebuild` 必须能复现并通过
- **Gate 5（Phase E 完成）**：`docker-compose up` 完整跑一遍真实查询
- **Gate 6（Phase F 完成）**：README 新手能按文档独立部署

---

## Rollback 点

- Phase A 失败：`BaseModel → BaseSettings` 有回归（比如 pydantic-settings 版本冲突）→ 临时 revert，env 覆盖走手动 `_apply_env_overrides`
- Phase B 失败：structlog 桥接 uvicorn 有副作用 → 回退到 stdlib logging + 简易 JSON formatter
- Phase D 失败：lifespan shutdown 流程阻塞过久 → 加 `asyncio.wait_for(..., timeout=cfg.server.shutdown_timeout_seconds)`
- Phase E 失败：镜像 >1GB → 检查是否 builder 阶段残留 / 调整 `apt-get clean` / torch 是否装了 CUDA 版（不应该）

Rollback 不影响已完成的 Phase。

---

## 估时总览

| Phase | 估时 | 累计 |
|-------|------|------|
| A 依赖&配置 | 0.5d | 0.5d |
| B 日志 | 1d | 1.5d |
| C 健康探针 | 0.5d | 2d |
| D Lifespan | 1d | 3d |
| E Docker | 1d | 4d |
| F 文档&收尾 | 0.5d | 4.5d |

**M1 总计约 4.5 人日**。B/C/D 有一定耦合（AppState 字段 + lifespan），E 相对独立。

---

## Out of Scope（再次强调）

本 implement.md 不覆盖：
- Prometheus `/metrics` → M4
- OpenTelemetry traces → M4
- API key / 限流 → M2
- 多 KB 隔离测试 → M2
- Eval 回归 → M3
- CI 构建镜像 / 推 registry → 本次 Phase E 只要本地能 build，CI 另开 task
