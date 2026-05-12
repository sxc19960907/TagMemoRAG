# implement.md — M2 实施 checklist

> 父文档：[prd.md](./prd.md) / [design.md](./design.md)
> 原则：自底向上，按 Phase 串行。每个 Phase 结束跑一次 `pytest`。

---

## Phase A — 数据契约与配置（~0.5 天）

- [ ] **A1** `src/tagmemorag/errors.py` 加三个错误码
  - `UNAUTHORIZED = "UNAUTHORIZED"` (401)
  - `FORBIDDEN = "FORBIDDEN"` (403)
  - `RATE_LIMITED = "RATE_LIMITED"` (429)
  - 对应自定义异常类：`UnauthorizedError / ForbiddenError / RateLimitedError`
  - 更新 `api.py::_status_for` 映射
- [ ] **A2** `src/tagmemorag/types.py` 加 `GraphState.anchors_version: int = 0`
- [ ] **A3** `src/tagmemorag/config.py` 加三段
  - `ApiKeyConfig`（id, hash, label, kb_allowlist, scopes, rate_limit_per_minute）
  - `AuthConfig`（enabled, backend, public_paths, global_max_rate_limit_per_minute, keys）
  - `RateLimitConfig`（enabled, default_per_minute, window_seconds）
  - `CacheConfig`（enabled, max_entries, ttl_seconds）
  - 加到 `Settings` 顶层
- [ ] **A4** `config.yaml` 补默认值（enabled: false 方便开发 / CI）
- [ ] **A5** `tests/unit/test_config_env.py` 加 M2 段覆盖
  - `TAGMEMORAG__AUTH__ENABLED=true` 能覆盖
  - `TAGMEMORAG__CACHE__MAX_ENTRIES=5000` 能覆盖

**验证**：`uv run pytest tests/unit/test_config_env.py tests/ -v` 全绿（50 + 新增几条）

---

## Phase B — 鉴权（~1.5 天）

- [ ] **B1** `src/tagmemorag/auth/__init__.py`（空包初始化）
- [ ] **B2** `src/tagmemorag/auth/base.py`
  - `ApiKey` frozen dataclass（`id / label / hash / kb_allowlist / scopes / rate_limit_per_minute / revoked / created_at / last_used_at`）
  - `allows_kb(kb_name)` / `has_scope(scope)` 方法
  - `AuthStore` ABC：`verify / list_keys / touch_usage`
- [ ] **B3** `src/tagmemorag/auth/config_store.py::ConfigAuthStore`
  - 从 `AuthConfig.keys` 构造
  - `verify` 用 `hmac.compare_digest` + 遍历（防 timing enum）
  - `hash` 格式 `"sha256:<hex>"`
- [ ] **B4** `src/tagmemorag/auth/dependencies.py`
  - `bearer_scheme = HTTPBearer(auto_error=False)`
  - `require_key(request, credentials)` → `ApiKey`（或 raise 401）
  - `require_scope(scope: str)` 工厂 → returns dependency
  - 处理 `auth.enabled=false` → 返回匿名 ApiKey
  - 处理 `public_paths` 豁免
  - `bind_contextvars(api_key_id=...)` 到 structlog
- [ ] **B5** CLI 子命令 `auth generate-key`
  - `src/tagmemorag/cli.py` 加 `auth` 子命令 + `generate-key` 动作
  - 用 `secrets.token_urlsafe(24)` 生成明文，前缀 `tmr_live_`
  - 输出 YAML 片段（运维复制到 config）+ 明文 key（客户端保存）
  - 明文绝不写文件，仅 stdout 一次
- [ ] **B6** `tests/unit/test_auth.py`
  - `ConfigAuthStore.verify` 成功/失败/revoked
  - 常数时间：多个 key 场景，伪造 key 耗时和真 key 相近（不严格定时，断言"遍历了所有 key"）
  - `require_key` 缺失 Authorization → 401
  - 非 Bearer scheme → 401
  - 错误 key → 401
  - 公共路径（`/health`）豁免
  - `auth.enabled=false` 任意请求都通
  - `require_scope("rebuild")` 只有 search scope → 403
  - `admin` scope 通过一切检查
  - `ApiKey.allows_kb` 空列表 / `["*"]` / 具体列表

**验证**：`uv run pytest tests/unit/test_auth.py tests/ -v` 全绿

---

## Phase C — 限流（~1 天）

- [ ] **C1** `src/tagmemorag/rate_limit/__init__.py`
- [ ] **C2** `src/tagmemorag/rate_limit/base.py`
  - `RateLimitResult` frozen dataclass（`allowed / remaining / limit / reset_epoch / retry_after_seconds`）
  - `RateLimitStore` ABC
- [ ] **C3** `src/tagmemorag/rate_limit/memory_sliding.py::InMemorySlidingWindowStore`
  - 滑动窗口计数（见 design §6）
  - `now_fn` 可注入
  - `threading.Lock` 保护
- [ ] **C4** `src/tagmemorag/auth/dependencies.py` 加 `rate_limit_dep`
  - 从 `app_state.rate_limiter` 取
  - 读取 `api_key.rate_limit_per_minute`（或默认）
  - 用 `min(..., auth.global_max_rate_limit_per_minute)` 兜底
  - 超限 → `RateLimitedError`（detail 含 `limit / retry_after_seconds`）
  - 把 `RateLimitResult` 存 `request.state.rate_limit`
- [ ] **C5** `src/tagmemorag/api.py` 新增 response middleware `rate_limit_headers`
  - 读 `request.state.rate_limit`，注入响应头 `X-RateLimit-*`
  - 超限时额外 `Retry-After`
- [ ] **C6** `tests/unit/test_rate_limit.py`
  - limit=3，发 3 次 allowed，第 4 次 denied
  - 推进 now_fn 跨过窗口 → 恢复 allowed
  - 两个 key_id 独立
  - 10 线程 × 10 次并发，总 allowed 数 = limit
  - `limit_per_minute=0` 时总是 deny
  - response 头 `X-RateLimit-Limit/Remaining/Reset` 正确
  - 超限响应含 `Retry-After`

**验证**：`uv run pytest tests/unit/test_rate_limit.py tests/ -v`

---

## Phase D — 缓存（~1 天）

- [ ] **D1** `src/tagmemorag/cache/__init__.py`
- [ ] **D2** `src/tagmemorag/cache/base.py::QueryCache` ABC（`get / set / clear`）
- [ ] **D3** `src/tagmemorag/cache/lru_ttl.py::LRUTTLCache`
  - `OrderedDict` + `threading.Lock`
  - `set(cache_key, value, kb_name="")` → 存 `(value, expiry, kb_name)`
  - `get` 过期直接删除并返回 None
  - `clear(kb_name)` 按 kb 过滤
- [ ] **D4** `src/tagmemorag/api.py` 加 `_compute_cache_key(req, state, settings)` 工具
  - question 归一化：`" ".join(q.strip().split())`
  - 用 `\0` 分隔 + sha256
- [ ] **D5** `/search` handler 改造
  - miss → 走 embedder + wave_search → cache.set
  - hit → 返回缓存 + 新 trace_id + 新 search_time_ms + `cache: "hit"`
  - 响应体加 `cache` 字段
- [ ] **D6** `src/tagmemorag/anchor.py::AnchorSystem`
  - `add` / `delete` 后 `self.state.anchors_version += 1`
  - `_persist()` 将 version 一起持久化
- [ ] **D7** `src/tagmemorag/storage/json_anchor.py`
  - `save(anchors, version=0)` 或把 version 作为 state 一起序列化
  - `anchors.json` schema 加 `version` 字段
  - `load` 时返回 `(anchors, version)`
- [ ] **D8** `src/tagmemorag/state.py::build_kb / load_kb`
  - 读写 anchors 时带上 version
  - `build_kb` 新图 anchors_version = 旧图的 + 1（或从 0 重新开始，文档化选择）
- [ ] **D9** `tests/unit/test_cache.py`
  - set/get round-trip
  - TTL 过期
  - LRU 超限淘汰
  - clear(kb_name=None) 全清
  - clear(kb_name="x") 只清 x
  - cache key 对所有参数敏感（参数不同 → miss）
  - 不同 kb_name → 不同 key
  - 不同 build_id → 不同 key
  - 不同 anchors_version → 不同 key
  - question 归一化（"  a  b  " 和 "a b" 命中同一 key）

**验证**：`uv run pytest tests/unit/test_cache.py tests/ -v`

---

## Phase E — 多 KB（~1.5 天）

- [ ] **E1** `src/tagmemorag/state.py::AppState` 升级
  - `kbs: dict[str, GraphState]`
  - `rebuild_locks: dict[str, threading.Lock]`
  - `get_kb / swap_kb / list_kbs / _lock_for` 方法
  - 保留 `current` property（`self.kbs.get("default")`）作为向后兼容（deprecated）或者删掉 M0 test 里的直接访问
  - `start_rebuild` 用 `_lock_for(kb_name)` 替代全局 `_rebuild_lock`
  - `_rebuild_worker` 调 `build_kb` 时只传入同名 KB 的旧状态：`old_state=self.kbs.get(kb_name)`，防止 anchors 从其他 KB 串入
  - shutdown drain 循环所有 kb 的 lock
- [ ] **E2** `src/tagmemorag/kb_manager.py`（可选，或直接把逻辑放 state.py）
  - `scan_and_load_all(settings, app_state)`：扫 `data/`，每个含 `meta.json` 的子目录调 `load_kb` 加载
  - 加载失败记 warning 不中断其他 KB
- [ ] **E3** lifespan startup 改造
  - warm-up embedder 后，调 `scan_and_load_all`
  - 装配依赖前设置 `app.state.settings = settings` 和 `app.state.app_state = app_state`，供 auth/rate-limit dependencies 读取
  - `logger.info("service_ready", kb_count=len(app_state.kbs))`
- [ ] **E4** `/search` / `/rebuild` / `/anchor*` handlers 全部按 `request.kb_name` 路由
- [ ] **E5** 新端点 `GET /kb`
  - 列出当前 ApiKey 可见的 KB（`allows_kb` 过滤）
  - 每个 entry: `{kb_name, build_id, node_count, anchors_version, status}`
- [ ] **E6** `/graph_info?kb_name=X` 继续工作
- [ ] **E7** 新端点 `POST /admin/cache/clear`
  - 受 `admin` scope 保护
  - body：`{"kb_name": "xxx"}` 可选
  - 调 `app_state.query_cache.clear(kb_name)`
  - 返回 `{"cleared_count": N}`
  - 日志 `cache_cleared`
- [ ] **E8** `tests/unit/test_multi_kb.py`
  - 构造两个 KB 到 tmp `data/` 下 → lifespan startup → `app_state.kbs` 有两个
  - 查询 kb_a 和 kb_b 各自独立
  - rebuild kb_a 时 kb_b 查询不受影响
  - `GET /kb` 返回按 allowlist 过滤后的列表
  - admin key 可见全部
  - rebuild kb_a 后 `POST /rebuild kb_a` 再次调用返回 409 `REBUILD_IN_PROGRESS`（同 KB 并发）
  - rebuild kb_a 的**同时** rebuild kb_b 可以并发通过（两个 lock 独立）

**验证**：`uv run pytest tests/unit/test_multi_kb.py tests/ -v`

---

## Phase F — API 装配 + E2E（~1 天）

- [ ] **F1** `src/tagmemorag/api.py` 所有端点加上鉴权依赖
  - `/search` → `require_scope("search")` + `rate_limit_dep` + body kb 检查
  - `/rebuild` POST → `require_scope("rebuild")` + rate_limit + kb 检查
  - `/rebuild/{task_id}` GET → `require_scope("rebuild")` + rate_limit
  - `/anchor` POST → `require_scope("anchor.write")` + rate_limit + kb 检查
  - `/anchor/{key}` DELETE → `require_scope("anchor.write")` + rate_limit
  - `/anchor` GET → `require_scope("search")` + rate_limit
  - `/graph_info` GET → `require_scope("search")` + rate_limit + kb 检查
  - `/kb` GET → `require_scope("search")`（不做 kb_name 检查，handler 内部过滤）
  - `/admin/cache/clear` → `require_scope("admin")`
- [ ] **F2** lifespan 装配所有 store
  - `auth_store = ConfigAuthStore(...)`
  - `rate_limiter = InMemorySlidingWindowStore(...)`
  - `query_cache = LRUTTLCache(...)` if enabled
  - 注入 `app_state`
- [ ] **F3** `tests/integration/test_m2_e2e.py`
  - 起 TestClient（auth.enabled=true，2 个 key：cs-a + admin）
  - 无 Authorization → 401
  - 错 key → 401
  - cs-a 访问 `/search` kb_name=allowed → 200
  - cs-a 访问 `/search` kb_name=disallowed → 403
  - cs-a 访问 `/rebuild` → 403（scope 不足）
  - admin 跨 KB 通过
  - 同 query 两次 → 第二次 `cache=hit` 且 `search_time_ms < 1`
  - rebuild 后同 query → `cache=miss`
  - /health 无需 key → 200
  - rate limit：cs-a 限 3/min，发 3 次 200，第 4 次 429 + `Retry-After`
- [ ] **F4** 回归：`uv run pytest tests/ -v` 全绿

---

## Phase G — 文档 & 收尾（~0.5 天）

- [ ] **G1** `README.md` 新增章节
  - 认证（Bearer token 示例）
  - 限流（响应头 + 429 示例）
  - 多 KB（同时构建多个，`GET /kb`）
  - 查询缓存（`cache: "hit"/"miss"` 字段，`/admin/cache/clear`）
  - API key 生成 CLI
- [ ] **G2** 更新 config.yaml 样例（含注释）
- [ ] **G3** `.env.example` 加 `TAGMEMORAG__AUTH__ENABLED`
- [ ] **G4** 跑一次完整回归
- [ ] **G5** 手工 smoke（真实 embedder + 真实 API key）
  ```bash
  python -m tagmemorag auth generate-key --id cs-test --scopes search --kb default --rate 10
  # 把输出里的 YAML 段粘到 config.yaml 的 auth.keys
  # 把明文 key 保存到 test.key
  python -m tagmemorag build --docs tests/fixtures --kb default
  python -m tagmemorag serve &
  curl -X POST http://127.0.0.1:8000/search \
    -H "Authorization: Bearer $(cat test.key)" \
    -H "Content-Type: application/json" \
    -d '{"question":"蒸汽很小"}'
  # 验证响应含 cache / trace_id / X-RateLimit-*
  ```
- [ ] **G6** commit + 归档任务

---

## 验证命令清单

```bash
# 单元
uv run pytest tests/unit/ -v

# 集成
uv run pytest tests/integration/ -v

# 全量回归
uv run pytest tests/ -v

# 手工生成一个开发 key
uv run python -m tagmemorag auth generate-key --id dev --scopes admin --rate 1000

# 鉴权开关（开发时关掉）
TAGMEMORAG__AUTH__ENABLED=false uv run python -m tagmemorag serve
```

---

## Review Gates

- **Gate 1（Phase B）**：`ConfigAuthStore.verify` 对正确/错误/revoked key 的返回值 + 常数时间实现（用 `hmac.compare_digest`）
- **Gate 2（Phase C）**：滑动窗口精度测试通过；并发测试通过；response 头正确
- **Gate 3（Phase D）**：cache key 对所有参数敏感；TTL/LRU 工作；`anchors_version` 正确递增并持久化
- **Gate 4（Phase E）**：两个 KB 真正独立并存；rebuild 不互相干扰；admin 跨 KB；allowlist 过滤 `/kb`
- **Gate 5（Phase F）**：E2E 端到端鉴权→限流→缓存→多 KB 全部通过
- **Gate 6（Phase G）**：README 示例能跑通

---

## Rollback 点

- Phase B 失败：暂时 `auth.enabled=false`，退化为 M1 行为
- Phase C 失败：`rate_limit.enabled=false` 跳过限流
- Phase D 失败：`cache.enabled=false` 跳过缓存
- Phase E 失败：保留单 KB 模式，只允许 `kb_name="default"`
- Phase F 失败：逐个端点加装，而不是全量

每层都是可 opt-in 的，失败可快速降级。

---

## 估时总览

| Phase | 估时 | 累计 |
|-------|------|------|
| A 契约&配置 | 0.5d | 0.5d |
| B 鉴权 | 1.5d | 2d |
| C 限流 | 1d | 3d |
| D 缓存 | 1d | 4d |
| E 多 KB | 1.5d | 5.5d |
| F API&E2E | 1d | 6.5d |
| G 文档&收尾 | 0.5d | 7d |

**M2 总计约 7 人日**。B/C/D 相对独立，E 依赖 B 的 ApiKey 契约，F 把所有组件装起来。

---

## Out of Scope（再次强调）

- 多副本 / leader election → post-v1
- Redis 限流/缓存 → post-v1（ABC 已预留）
- SQLite/Vault key 后端 → post-v1（ABC 已预留）
- 动态 API key CRUD（POST/DELETE /auth/keys）→ post-v1
- Prometheus metrics → M4
- OpenTelemetry → M4
- Eval 回归 → M3
