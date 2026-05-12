# design.md — M1 运维基础技术设计

> 约束：本文档只覆盖 M1 里程碑。M2-M4 在此架构上叠加，不改核心。
> 父文档：[prd.md](./prd.md)
> 依赖基座：M0 的 `AppState / lifespan / config.py / errors.py`

---

## 1. 模块边界与改动范围

```
┌──────────────────────────────────────────────────────────┐
│ Container (Docker)                                        │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │ uvicorn process                                    │  │
│  │                                                    │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │ FastAPI app (api.py)                         │  │  │
│  │  │                                              │  │  │
│  │  │  ├── /health, /ready (M1 new)                │  │  │
│  │  │  ├── /search, /rebuild, /anchor (M0)         │  │  │
│  │  │  └── middleware: trace_id injection (M1 new) │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │                                                    │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │ lifespan (M1 upgraded)                       │  │  │
│  │  │  startup:  configure_logging → load embedder │  │  │
│  │  │           → warmup → load_kb → mark_ready    │  │  │
│  │  │  shutdown: mark is_shutting_down             │  │  │
│  │  │           → await rebuild_lock               │  │  │
│  │  │           → release resources                │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │                                                    │  │
│  │  AppState (M0 + M1 flags)                         │  │
│  │  Embedder (M0, now warmed up at startup)          │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  env: HF_HUB_OFFLINE=1, TAGMEMORAG__*                    │
│  volumes: /app/data (KB persistence)                      │
│  USER: app (non-root)                                    │
└──────────────────────────────────────────────────────────┘
```

**改动清单**（M0 → M1 差异）：

| 模块 | 类型 | 改动摘要 |
|------|------|----------|
| `pyproject.toml` | edit | 加 `structlog`, `pydantic-settings` 依赖 |
| `src/tagmemorag/config.py` | edit | `BaseModel → BaseSettings` + env 映射 |
| `src/tagmemorag/logging_setup.py` | new | structlog configure + uvicorn 桥接 |
| `src/tagmemorag/errors.py` | edit | 新增 `SHUTTING_DOWN` 错误码 |
| `src/tagmemorag/state.py` | edit | 加 `embedder_ready / is_shutting_down` 字段 |
| `src/tagmemorag/api.py` | edit | `/health` `/ready` 端点 + trace_id 中间件 + lifespan 改造 |
| `src/tagmemorag/cli.py` | edit | `serve` 前先 `configure_logging()`；serve 默认从 `Settings.server` 读取 host/port，CLI args 显式覆盖 |
| `Dockerfile` | new | multi-stage |
| `docker-compose.yml` | new | dev + prod profile |
| `.dockerignore` | new | 过滤 .venv/data/.trellis/tests |
| `.env.example` | new | 示例 env 变量 |
| `config.yaml` | edit | 加 `logging / server` 段 |
| `tests/unit/test_logging.py` | new | 结构化字段断言 |
| `tests/unit/test_health.py` | new | /health /ready 行为 |
| `tests/unit/test_config_env.py` | new | env override 覆盖 |
| `tests/unit/test_shutdown.py` | new | SIGTERM 行为 |
| `README.md` | edit | Docker 部署 + env 变量章节 |

---

## 2. 数据契约变更

### 2.1 Settings（env 化）

```python
# src/tagmemorag/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAGMEMORAG__",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    model: ModelConfig = ...
    graph: GraphConfig = ...
    search: SearchConfig = ...
    parser: ParserConfig = ...
    storage: StorageConfig = ...
    server: ServerConfig = ...            # M1 new
    logging: LoggingConfig = ...          # M1 new


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    shutdown_timeout_seconds: int = 60

class LoggingConfig(BaseModel):
    level: str = "INFO"                   # DEBUG / INFO / WARNING / ERROR
    format: Literal["json", "console"] = "json"   # console 仅开发用
```

**Env 覆盖示例**：
```
TAGMEMORAG__SERVER__PORT=9000
TAGMEMORAG__LOGGING__LEVEL=DEBUG
TAGMEMORAG__MODEL__NAME=BAAI/bge-base-zh-v1.5
TAGMEMORAG__STORAGE__DATA_DIR=/data
```

**CLI / env precedence**:
- `load_config()` semantics remain `env > yaml > defaults`.
- `python -m tagmemorag serve` must use `cfg.server.host` and `cfg.server.port` by default.
- `python -m tagmemorag serve --host ... --port ...` explicitly overrides env/YAML for that process only.
- Docker CMD must call `serve` without hardcoded host/port so container env remains authoritative.

**load_config()** 合并语义：
```python
def load_config(path: str | Path = "config.yaml") -> Settings:
    yaml_data = {}
    if Path(path).exists():
        yaml_data = yaml.safe_load(Path(path).read_text()) or {}
    # BaseSettings 构造时：env > init kwargs > defaults
    # 我们用 init kwargs 传 yaml_data → 效果：env > yaml > defaults
    return Settings(**yaml_data)
```

### 2.2 AppState 新增字段

```python
class AppState:
    ...
    embedder_ready: bool = False          # warm-up 完成后置 True
    is_shutting_down: bool = False        # SIGTERM 后置 True

    def mark_embedder_ready(self) -> None:
        with self._lock:
            self.embedder_ready = True

    def begin_shutdown(self) -> None:
        with self._lock:
            self.is_shutting_down = True
```

### 2.3 ErrorCode 新增

```python
class ErrorCode(StrEnum):
    ...  # M0 已有
    SHUTTING_DOWN = "SHUTTING_DOWN"
```

---

## 3. 结构化日志设计（structlog）

### 3.1 配置入口

```python
# src/tagmemorag/logging_setup.py
import logging
import sys
import structlog

def configure_logging(level: str = "INFO", format: str = "json") -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,   # 从 contextvars 注入 trace_id 等
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging (uvicorn / fastapi) → structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
```

### 3.2 trace_id 中间件

```python
# 在 api.py 里
import uuid
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

@app.middleware("http")
async def trace_middleware(request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    clear_contextvars()
    bind_contextvars(trace_id=trace_id, path=request.url.path, method=request.method)
    try:
        response = await call_next(request)
    finally:
        clear_contextvars()
    response.headers["X-Trace-Id"] = trace_id
    return response
```

### 3.3 关键事件清单

| Event key | 触发点 | 字段 |
|-----------|--------|------|
| `service_starting` | lifespan startup 开始 | version, config_path |
| `model_loaded` | embedder 初始化完成 | model_name, device, duration_ms |
| `model_warmed_up` | warm-up encode 完成 | duration_ms |
| `kb_loaded` | load_kb 成功 | kb_name, build_id, node_count |
| `kb_load_skipped` | load_kb KbNotLoadedError | kb_name |
| `service_ready` | /ready 首次可返回 200 | startup_duration_ms |
| `search` | /search 结束 | query_len, top_k, result_count, latency_ms, build_id |
| `rebuild_started` | POST /rebuild 受理 | task_id, docs_dir, kb_name |
| `rebuild_done` | worker 完成 | task_id, build_id, duration_ms, chunk_count |
| `rebuild_failed` | worker 异常 | task_id, error_type, error_message |
| `anchor_created` / `anchor_deleted` | /anchor 操作 | anchor_key, label |
| `shutdown_started` | SIGTERM 捕获 | |
| `rebuild_drained` | shutdown 等到 _rebuild_lock | wait_ms |
| `shutdown_complete` | lifespan shutdown 退出 | total_ms |
| `request_error` | 全局 exception handler | code, status, exception_type |

---

## 4. 健康 / 就绪探针

### 4.1 端点契约

```python
from fastapi.responses import PlainTextResponse

@app.get("/health", include_in_schema=False)
def health() -> PlainTextResponse:
    return PlainTextResponse("ok", status_code=200)

@app.get("/ready", include_in_schema=False)
def ready() -> PlainTextResponse:
    if app_state.is_shutting_down:
        return PlainTextResponse("shutting down", status_code=503)
    if not app_state.embedder_ready:
        return PlainTextResponse("embedder not ready", status_code=503)
    if app_state.current is None:
        return PlainTextResponse("kb not loaded", status_code=503)
    return PlainTextResponse("ok", status_code=200)
```

**注意事项**：
- `include_in_schema=False` — 不进 OpenAPI doc
- **不走** `ServiceError` 统一错误格式 — K8s probe 只认 HTTP status
- 响应时间必须 <10ms，不做额外计算

### 4.2 probe 配置推荐（写进 README）

```yaml
# K8s
livenessProbe:
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet: { path: /ready, port: 8000 }
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2

startupProbe:
  httpGet: { path: /ready, port: 8000 }
  periodSeconds: 5
  failureThreshold: 24   # 容忍冷启动 2 分钟

terminationGracePeriodSeconds: 60
```

---

## 5. Lifespan 启动 / 关闭时序

### 5.1 startup

```
1. configure_logging(cfg.logging.level, cfg.logging.format)
2. structlog.info("service_starting", version=..., config_path=...)
3. t0 = time.monotonic()
4. app.state.embedder = create_embedder(cfg.model.*)
   → structlog.info("model_loaded", duration_ms=...)
5. try: embedder.encode_query("warmup")
         app_state.mark_embedder_ready()
         structlog.info("model_warmed_up", duration_ms=...)
   except Exception:
         structlog.error("model_warmup_failed")
         sys.exit(1)
6. try: state = load_kb("default", cfg)
         app_state.swap(state)
         structlog.info("kb_loaded", kb_name="default", build_id=..., node_count=...)
   except KbNotLoadedError:
         structlog.warning("kb_load_skipped", kb_name="default")
7. structlog.info("service_ready", startup_duration_ms=time.monotonic()-t0 ...)
8. yield  # FastAPI 对外服务
```

### 5.2 shutdown

```
1. structlog.info("shutdown_started")
2. app_state.begin_shutdown()
3. t0 = time.monotonic()
4. # 等待 in-flight rebuild 完成（阻塞获取 lock 再立刻释放）
   await asyncio.to_thread(app_state._rebuild_lock.acquire)
   app_state._rebuild_lock.release()
   structlog.info("rebuild_drained", wait_ms=...)
5. # uvicorn 会在 lifespan shutdown 返回后继续等 in-flight HTTP 请求
   # 不需要我们再做额外 drain
6. structlog.info("shutdown_complete", total_ms=...)
```

### 5.3 信号流

```
SIGTERM ──▶ uvicorn signal handler ──▶ 停止接收新连接 + 触发 lifespan shutdown
                                   │
                                   └─▶ 已接收的 HTTP 请求继续处理
                                       直到 graceful timeout (default 60s)

lifespan shutdown ──▶ app_state.begin_shutdown()  (新 /rebuild → 503)
                 ──▶ 等 _rebuild_lock
                 ──▶ 返回

uvicorn ──▶ 等 in-flight HTTP 结束
        ──▶ 进程退出 (code 0)
```

### 5.4 并发 rebuild 在 shutdown 期间

```python
# state.py
def start_rebuild(self, ...):
    if self.is_shutting_down:
        raise ServiceError(ErrorCode.SHUTTING_DOWN, "Service is shutting down.")
    if not self._rebuild_lock.acquire(blocking=False):
        raise RebuildInProgressError(...)
    ...
```

---

## 6. Dockerfile 详细设计

### 6.1 Stage 1 — builder

```dockerfile
FROM python:3.11-slim-bookworm AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# uv
ADD https://astral.sh/uv/install.sh /tmp/uv-install.sh
RUN sh /tmp/uv-install.sh && rm /tmp/uv-install.sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# 装生产依赖到本地 .venv
RUN uv sync --frozen --no-dev

# 预下载模型（走默认缓存 ~/.cache/huggingface/hub/）
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"
```

### 6.2 Stage 2 — runtime

```dockerfile
FROM python:3.11-slim-bookworm

RUN groupadd -r app && useradd -r -g app -m -d /home/app app

WORKDIR /app

# Copy venv + model cache + app code
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /root/.cache/huggingface /home/app/.cache/huggingface
COPY --chown=app:app src ./src
COPY --chown=app:app config.yaml ./

# Data dir (will be mounted as volume)
RUN mkdir -p /app/data && chown -R app:app /app /home/app

ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/home/app/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TAGMEMORAG__STORAGE__DATA_DIR=/app/data \
    TAGMEMORAG__SERVER__HOST=0.0.0.0 \
    TAGMEMORAG__SERVER__PORT=8000

USER app
EXPOSE 8000

CMD ["python", "-m", "tagmemorag", "serve"]
```

### 6.3 docker-compose.yml

```yaml
services:
  tagmemorag:
    build: .
    image: tagmemorag:m1
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      TAGMEMORAG__LOGGING__LEVEL: INFO
      TAGMEMORAG__SERVER__HOST: 0.0.0.0
      TAGMEMORAG__SERVER__PORT: "8000"
      TAGMEMORAG__SERVER__SHUTDOWN_TIMEOUT_SECONDS: "60"
    healthcheck:
      # Compose liveness-style healthcheck: empty KB containers should remain running.
      # Use /ready for K8s readiness, not docker-compose health.
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 30s
    stop_grace_period: 60s
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp
```

### 6.4 .dockerignore

```
.venv/
data/
.trellis/
.pytest_cache/
__pycache__/
*.pyc
*.egg-info/
.git/
.claude/
.codex/
.agents/
tests/
*.md
!README.md
```

---

## 7. 测试策略

| 测试 | 文件 | 覆盖范围 |
|------|------|---------|
| env override | `tests/unit/test_config_env.py` | `TAGMEMORAG__SERVER__PORT=9000` → `cfg.server.port == 9000`；YAML + env 优先级 |
| JSON 日志格式 | `tests/unit/test_logging.py` | `configure_logging("json")` 后 structlog 输出含 `timestamp / level / event / trace_id` |
| trace_id 中间件 | `tests/unit/test_api_trace.py` | 响应头 `X-Trace-Id` 存在；log 记录能读到 trace_id |
| /health | `tests/unit/test_health.py` | 无论状态都 200，text/plain "ok" |
| /ready 四种状态 | `tests/unit/test_health.py` | `embedder_ready=F / T, current=None / not-None, is_shutting_down=F / T` 组合 |
| shutdown drain | `tests/unit/test_shutdown.py` | 起 rebuild → 触发 lifespan shutdown → 断言 rebuild 完成 + shutdown 正常退出 |
| rebuild 被拒（shutdown） | `tests/unit/test_shutdown.py` | `is_shutting_down=True` 时 /rebuild → 503 `SHUTTING_DOWN` |
| Dockerfile 冒烟 | `tests/integration/test_docker.py`（可选） | `docker build .` + `curl /health`，再准备 KB 后 `curl /ready` |

---

## 8. README.md 新增内容（草稿）

### Docker 部署

```bash
docker build -t tagmemorag:m1 .
docker-compose up -d

curl http://127.0.0.1:8000/health   # 200 ok
curl http://127.0.0.1:8000/ready    # 200 ok / 503 ...
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TAGMEMORAG__SERVER__PORT` | 8000 | HTTP port |
| `TAGMEMORAG__SERVER__SHUTDOWN_TIMEOUT_SECONDS` | 60 | graceful shutdown budget |
| `TAGMEMORAG__LOGGING__LEVEL` | INFO | DEBUG / INFO / WARNING / ERROR |
| `TAGMEMORAG__LOGGING__FORMAT` | json | json / console |
| `TAGMEMORAG__MODEL__NAME` | BAAI/bge-small-zh-v1.5 | embedder model |
| `TAGMEMORAG__STORAGE__DATA_DIR` | ./data | KB persistence root |
| `TAGMEMORAG__SEARCH__AGGREGATE` | max | max / sum |

---

## 9. 错误 / 失败处理

| 场景 | 行为 |
|------|------|
| warm-up encode 失败 | log error → `sys.exit(1)` → K8s 重启 |
| load_kb 失败（目录不存在） | log warning `kb_load_skipped` → `/ready` 返回 503 → 等运维 `POST /rebuild` |
| trace_id 生成失败（几乎不可能） | fallback `"unknown-trace"` |
| shutdown 等 rebuild 超过 terminationGracePeriodSeconds | K8s SIGKILL → 数据原子写保证一致 |
| 并发 rebuild 在 shutdown 期间 | 503 `SHUTTING_DOWN` |

---

## 10. 不做什么（重申）

- Prometheus `/metrics` 端点 → M4
- OpenTelemetry traces → M4
- API key / 限流 / 多 KB 测试 → M2
- Eval 回归 → M3
- HA 多副本 → post-v1

---

## 附：字段可追溯性

| PRD 决策 | design 对应段 |
|----------|--------------|
| structlog 日志 | §3 |
| pydantic-settings env 覆盖 | §2.1 |
| /ready = embedder + KB | §4.1 + §2.2 |
| 镜像预打包模型 | §6.1 |
| multi-stage Dockerfile | §6 |
| 等 search + 等 rebuild shutdown | §5.2-5.3 |
| SHUTTING_DOWN 错误码 | §2.3 + §5.4 |
