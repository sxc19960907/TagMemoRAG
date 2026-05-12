# brainstorm: M1 运维基础（容器化 + 可观测 + 健康探针）

## Goal

把 M0 的"单节点本地可跑"升级为"容器化可部署的生产形态"。覆盖容器镜像、结构化日志、健康/就绪探针、优雅关闭、环境变量配置覆盖、模型冷启动预热。

这是 v1 路线图的第二个里程碑，完成后 TagMemoRAG 可以在任何支持容器的平台（docker-compose / K8s / ECS）直接部署，运维可以通过标准 K8s probe 接入监控。

## Background / Known Context

### M0 的状态（已交付）
- `src/tagmemorag/api.py` — FastAPI app，`lifespan` 里懒初始化 embedder 并尝试加载 default KB
- `src/tagmemorag/config.py` — Pydantic `Settings`，`load_config(path)` 读 YAML
- `src/tagmemorag/cli.py` — `serve` 命令走 `uvicorn.run("tagmemorag.api:app")`
- `src/tagmemorag/errors.py` — 统一错误格式 `{code, message, detail}`
- `src/tagmemorag/state.py` — `AppState` + `build_kb` + `load_kb` + double-buffer rebuild
- 依赖：sentence-transformers / networkx / fastapi / uvicorn / pydantic / pyyaml
- 真实模型验证过：BGE-small-zh-v1.5，16 chunk 冷启动约 5s，查询 <100ms

### M0 预留的钩子（M1 要接上）
- M0 的 `/search` 已返回 `search_time_ms`，但尚未有统一 `search_with_metrics(...)` 封装或结构化日志事件 — M1 应该把 trace_id / log 结构落地
- `/health` / `/ready` 在 design §4.4 写了要实现，M0 跳过了（只留 `AppState._current is not None` 的 getter 思路）
- 环境变量 override config 在 M0 Out of Scope 里，M1 必须做

### M1 在 PRD §Milestones 里的定义（M0 的 prd.md）
> **M1 运维基础** | Dockerfile/compose / JSON 日志 / `/health`,`/ready` / 优雅关闭 / 配置环境变量化 / 模型 warm-up

## Assumptions (temporary)

- 目标部署平台：docker-compose（开发/演示）+ K8s（生产）— 两者 probe 语义一致
- 日志目的地：stdout/stderr（12-factor）— 容器平台收集
- 镜像体积：< 1GB 是可接受的（sentence-transformers + torch 本来就大）
- Python 3.11 slim 作为基础镜像
- M1 不做 Prometheus `/metrics`（那是 M4）
- M1 不做 API key / 限流（那是 M2）
- M1 不做 Eval 回归（那是 M3）

## Decision (ADR-lite)

### Decision: 日志库 = structlog

**Context**：M1 需要 JSON 结构化日志 → stdout，为 M4 OTel 接入铺路。候选：stdlib logging + python-json-logger / structlog / loguru。

**Decision**：选 **structlog**。

**Rationale**：
- 结构化原生 API（`logger.info("search", trace_id=...)`），不需要 `extra={}` 调用风格
- `structlog.contextvars.bind_contextvars(trace_id=...)` 通过 contextvars 自动 propagate 到同请求的所有日志
- 可桥接 uvicorn / FastAPI / stdlib logging，不留孤岛
- M4 接 OTel 有现成 processor，零改动

**Consequences**：
- 新依赖：`structlog>=24.1`（纯 Python，无底层依赖，约 200KB）
- 启动时要做一次 `structlog.configure(...)` 全局配置
- CLI 的 `build` 命令也走同一套日志配置，保持 API/CLI 日志格式一致

### Decision: 环境变量覆盖 = pydantic-settings 自动映射

**Context**：M0 用 YAML + Pydantic Settings。M1 要让 env 覆盖，不想手维护 env 列表。

**Decision**：把 `Settings(BaseModel)` 升级为 `Settings(BaseSettings)`（pydantic-settings 库），env 自动映射到嵌套字段。

**约定**：
- 前缀：`TAGMEMORAG__`
- 嵌套分隔符：双下划线（`TAGMEMORAG__MODEL__NAME=xxx` → `settings.model.name`）
- 优先级：env > `.env` file > `config.yaml` > Pydantic defaults
- 敏感值（未来的 API key）标记为 `SecretStr`，日志打印时自动 masked
- `load_config()` 合并顺序：YAML 读入 → 创建 Settings 时 env 自动覆盖

**Rationale**：
- 零维护成本：Settings 加字段 = env 自动可覆盖
- K8s ConfigMap / Helm values 友好（双下划线嵌套是业界惯例）
- `.env` 自动支持，本地开发零破坏
- M0 的 `conftest.py` 里 `Settings(storage=..., model=...)` 构造方式兼容

**Consequences**：
- 新依赖：`pydantic-settings>=2.2`（pydantic 生态内，约 50KB）
- `config.py` 有一处改动：`BaseModel → BaseSettings` + `model_config = SettingsConfigDict(env_prefix="TAGMEMORAG__", env_nested_delimiter="__", env_file=".env")`
- YAML 仍然可用（`load_config(path)` 逻辑保持），env 只做覆盖

### Decision: `/ready` 语义 = embedder warm-up + KB 加载都完成

**Context**：K8s readiness probe 用 `/ready` 决定是否把流量打进来。三个层次的资源（进程/embedder/KB）要选一个作为 ready 的门槛。

**Decision**：`/ready` 返回 200 当且仅当：
1. Embedder 已加载且完成一次 warm-up encode（证明模型可用）
2. `AppState.current` 非空（KB 已加载）

否则返回 **503 text/plain "not ready"**。

**配套规则**：
- `/health` 永远返回 **200 text/plain "ok"**（只证明进程活着）
- 两个端点**不走统一错误格式**（K8s probe 只需要 HTTP status code 和短文本，简单越好）
- 两端点和主 API 共用 8000 端口（独立端口留给 M4 观测）
- `/rebuild` / `/health` **不依赖 `/ready`**，运维可以在 `/ready=503` 时通过 `/rebuild` 推数据 KB
- `AppState` 增加一个 `embedder_ready: bool` 字段，warm-up 完成后置 true

**Rationale**：
- "Ready" = "可以处理业务请求"，K8s 不会把流量打到还没准备好的 Pod，避免 503/404 噪音
- `/rebuild` 不看 `/ready` 保证空 KB 容器也能被运维初始化
- 简单 text/plain 响应对 K8s / curl-check 最友好

**Consequences**：
- `AppState` 新增 `embedder_ready` + `mark_embedder_ready()` 方法
- `/ready` 访问 `app_state` 和 `embedder`，判断顺序：embedder_ready → app_state.current
- 首次部署 KB 空 → 503 → 运维调 `/rebuild` → KB 加载 → 200

### Decision: 模型分发 = 镜像预打包 + 启动时 warm-up

**Context**：M1 要让容器能离线部署（K8s 内网环境常无外网）。模型分发三种方式：运行时下载 / 镜像预打包 / 挂载卷。

**Decision**：
- Dockerfile 里执行 `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"`，把模型预下载到镜像的 `~/.cache/huggingface/hub/`
- 容器 `HF_HUB_OFFLINE=1`，拒绝运行时外网访问（启动失败比静默加载错模型好）
- `lifespan` 里做一次 `embedder.encode_query("warmup")`，测耗时并打 `model_warmed_up` 日志
- warm-up 失败 → 进程直接 `sys.exit(1)`，让 K8s 负责重启

**Rationale**：
- 生产级 = 离线可部署
- 冷启动时间可预期（不依赖网络）
- 镜像大小可接受（~1GB，在 NFR 预算内）
- 换模型的成本（重建镜像）是合理代价

**Consequences**：
- 镜像构建时间增加（~30s 下载 + 打包）
- 镜像体积 ~1GB（符合 acceptance 中的 <1GB 边界，略紧）
- `HF_HUB_OFFLINE=1` 意味着开发镜像和生产镜像共用一份，本地调试换模型需要 rebuild
- 多模型场景 post-v1 再考虑切回挂载卷方案

### Decision: 镜像构建 = multi-stage（builder + runtime），uv 装依赖

**Context**：选定 multi-stage 作为镜像构建策略。需要确定 base 镜像、依赖安装方式、非 root 运行。

**Decision**：
- Base：`python:3.11-slim-bookworm`（两阶段都用）
- 依赖管理：**`uv sync --frozen --no-dev`** 安装到 `.venv/`，runtime `COPY --from=builder` 过来
- 模型文件：`builder` 里 `SentenceTransformer('BAAI/bge-small-zh-v1.5')` 预下载，`COPY --from=builder /root/.cache/huggingface`
- 运行用户：`app:app`（非 root），UID/GID 自动分配
- 环境变量：`HF_HOME / HF_HUB_OFFLINE=1 / PYTHONDONTWRITEBYTECODE=1 / PYTHONUNBUFFERED=1`
- 入口：`CMD ["python", "-m", "tagmemorag", "serve"]`
- `serve` 命令默认读取 `Settings.server.host/port`；CLI 参数显式传入时覆盖 env/YAML
- 只读文件系统兼容：`/app/data` 挂载 volume，`/tmp` 用 tmpfs

**Rationale**：
- multi-stage 是 Python 生产镜像的业界标准
- uv 装依赖比 pip 快 ~10x，lock 文件保证可复现构建
- 非 root 运行符合安全基线
- 只读文件系统兼容是 K8s `readOnlyRootFilesystem: true` 的前置

**Consequences**：
- 最终镜像 ~950MB（torch CPU wheel 是大头，无法压缩）
- builder 阶段 ~1.5GB（含构建工具链），最终不保留
- `pyproject.toml` 的 `[dev]` 依赖不进 runtime
- `config.yaml` 拷进镜像作为默认，env 可覆盖。不要在 Docker CMD 里硬编码 `--host/--port`，否则 `TAGMEMORAG__SERVER__PORT` 无法影响实际监听端口。

**具体 Dockerfile 形态**（design.md 里详细写）：
- Stage 1 `builder`：slim + build-essential + curl + uv → `uv sync --frozen --no-dev` + 模型预下载
- Stage 2 `runtime`：slim + `app` 用户 + venv/hf_cache/src COPY → `CMD serve`

### Decision: 优雅关闭 = 等 in-flight search + 等 in-flight rebuild

**Context**：SIGTERM 到来时如何处理进行中的 search 请求和 rebuild 后台线程。

**Decision**：
- uvicorn 负责等 in-flight HTTP 请求（含 `/search`）完成 — 靠 uvicorn 原生 graceful shutdown
- FastAPI `lifespan` shutdown 段等 `AppState._rebuild_lock` 释放（rebuild 完成才让进程退出）
- `AppState` 新增 `is_shutting_down: bool`，SIGTERM 后新 rebuild 请求返回 `503 SHUTTING_DOWN`（新 search 请求仍然处理，直到 lifespan 结束）
- `terminationGracePeriodSeconds` 默认 60s，超时 K8s SIGKILL（原子写保证磁盘一致）
- structlog 打 `shutdown_started` / `rebuild_drained` / `shutdown_complete` 三条事件

**Rationale**：
- rebuild 完成后 `save_kb` 已调用，新图持久化 → 重启后直接可用，无需运维重试
- `_rebuild_lock` 已是 M0 架构里的协调点，复用零代价
- 60s 预算覆盖 10k 节点 rebuild；极端超长 rebuild 被 SIGKILL 时 tmp 文件会泄漏但最终文件原子，可接受

**Consequences**：
- `AppState` 新增 `is_shutting_down` + 关闭期间拒绝新 rebuild
- 新增错误码 `SHUTTING_DOWN` → 503
- K8s / docker-compose 配置示例里说明 `terminationGracePeriodSeconds=60` 的必要性
- 测试：pytest 启动 rebuild → 触发 shutdown → 断言 rebuild 完成 + 进程正常退出

## Open Questions (blocking / preference)

1. ~~日志库选型~~ → **structlog** (decided)
2. ~~环境变量覆盖语义~~ → **pydantic-settings 自动映射** (decided)
3. ~~`/ready` 就绪语义~~ → **embedder warm-up + KB 加载都完成** (decided)
4. ~~模型 warm-up 策略~~ → **镜像预打包 + HF_HUB_OFFLINE=1** (decided)
5. ~~镜像策略~~ → **multi-stage（builder + runtime），uv 装依赖** (decided)
6. ~~优雅关闭范围~~ → **等 search + 等 rebuild，terminationGracePeriod 60s** (decided)

所有 M1 核心决策已锁定，进入 design.md / implement.md 撰写。

## Requirements (草稿，brainstorm 期间细化)

### 1. Docker 化
- `Dockerfile`（multi-stage 或 slim）
- `docker-compose.yml`（dev + prod 两份或一份带 profile）
- `.dockerignore` 过滤 `.venv / data / .trellis / tests` 等
- Compose healthcheck 使用 `/health`，避免空 KB 首次启动时因 `/ready=503` 被标记为 unhealthy；K8s readiness probe 使用 `/ready`

### 2. 结构化日志
- JSON 格式 → stdout
- 每条日志至少含 `ts / level / event / trace_id / build_id / kb_name`（相关时）
- `api.py` 里对 `/search` / `/rebuild` / anchor ops 打结构化日志
- `trace_id` 通过 request 中间件生成并注入到 response 头

### 3. 健康探针
- `GET /health` — 进程存活，永远返回 200（除非进程死了）
- `GET /ready` — KB 已加载 + embedder 就绪才返回 200，否则 503
- K8s probe 友好：无需身份验证，快速返回

### 4. 优雅关闭
- SIGTERM → FastAPI `lifespan` shutdown hook
- 等待 in-flight requests 完成（uvicorn 原生支持）
- 关闭逻辑：等待 in-flight rebuild 完成（复用 M0 rebuild lock，不取消线程）
- 默认 timeout 60s

### 5. 环境变量覆盖
- 约定前缀 `TAGMEMORAG__`
- 嵌套用 `__` 分隔（例：`TAGMEMORAG__MODEL__NAME=xxx`）
- 优先级：env > yaml > default

### 6. 模型 warm-up
- 启动时预加载 embedder 并 encode 一次短文本
- warm-up 期间 `/ready` 返回 503
- warm-up 完成后日志输出 `model_loaded` 事件 + 耗时

## Acceptance Criteria (evolving)

功能：
- [ ] `docker build .` 成功，镜像大小 < 1GB
- [ ] `docker-compose up` 后 `curl /health` 返回 200
- [ ] KB 未加载时 `/ready` 返回 503；加载或 rebuild 后返回 200
- [ ] `/search` 日志包含 `trace_id / build_id / query_len / latency_ms / result_count`
- [ ] `SIGTERM` 后等待 in-flight 请求和 rebuild 完成再退出（默认预算 60s）
- [ ] `TAGMEMORAG__SERVER__PORT=9000` 能覆盖 YAML 里的 port，并且 `python -m tagmemorag serve` 实际监听 9000
- [ ] 模型 warm-up 完成前 `/ready` 是 503，完成后 200
- [ ] 响应头包含 `X-Trace-Id`
- [ ] `docker run` 无需 GPU、无需 root、只读文件系统兼容（`data/` 挂载 volume）

性能：
- [ ] 冷启动到 `/ready` = 200 的耗时 < 20s（含模型下载后的二次启动）
- [ ] 结构化日志不阻塞请求（异步写或直接 stdout）

## Definition of Done

- 单元测试：env override / log format / health+ready 行为
- 集成测试：docker-compose 启动 + curl 全端点
- 文档：README.md 新增 "Docker 部署" 和 "环境变量" 章节

## Out of Scope (explicit)

- Prometheus `/metrics` 端点 → M4
- OpenTelemetry traces → M4
- API key / 限流 → M2
- Eval 回归 → M3
- HA 多副本 → post-v1
- 模型体积优化（量化/剪枝）→ post-v1

## Technical Notes

- 目标基础镜像：`python:3.11-slim-bookworm`
- M0 代码里 `HashingEmbedder` 保留（测试用），M1 不动
- 依赖：可能要加 `python-json-logger`（日志库选型后定）

## Completion Notes

M1 is functionally complete as of 2026-05-12:

- Docker image builds and runs.
- `/health` and `/ready` probes work as designed.
- JSON logs, request trace IDs, env overrides, model warm-up, and graceful shutdown are implemented.
- HTTP embedding provider is implemented and verified against SiliconFlow with `Qwen/Qwen3-VL-Embedding-8B`.
- Docker smoke test succeeded: mounted docs -> `/rebuild` -> `/ready=200` -> `/search`.
- Test suite passes: `uv run pytest tests/ -v` -> 46 passed.

Known follow-up:

- The local-model Docker image is still oversized (`tagmemorag:m1` measured about 2.25GB). The main cause is the local ML runtime stack (`torch`, `transformers`, `scipy`, `scikit-learn`) plus model cache. Track this as a post-M1 optimization: build a lightweight HTTP-embedding image/profile that excludes local model dependencies and relies on `model.provider=http`.
