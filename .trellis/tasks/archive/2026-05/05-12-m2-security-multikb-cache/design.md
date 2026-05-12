# design.md — M2 安全 + 多KB + 缓存技术设计

> 约束：本文档只覆盖 M2 里程碑。M3 Eval / M4 观测 / post-v1 HA 在此架构上叠加。
> 父文档：[prd.md](./prd.md)
> 依赖基座：M0 存储分层 + M1 AppState/lifespan/structlog/pydantic-settings

---

## 1. 模块边界与改动范围

```
┌────────────────────────────────────────────────────────────┐
│ FastAPI app (api.py)                                       │
│                                                            │
│  Middleware chain (在 handler 之前，按序执行):               │
│  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ Trace ID   │ │ Authn    │ │ Authz    │ │ RateLimit│    │
│  │ (M1)       │→│ Bearer   │→│ scope+kb │→│ sliding  │    │
│  └────────────┘ └──────────┘ └──────────┘ └──────────┘    │
│                     │            │            │             │
│                     ▼            ▼            ▼             │
│              AuthStore    ApiKey 上下文   RateLimitStore    │
│                                                             │
│  Endpoint handlers (cache 检查在 handler 内部):             │
│    /search → QueryCache.get → miss → wave_search → set      │
│    /rebuild → KBManager.start_rebuild                       │
│    /anchor* → AnchorSystem + invalidate-like行为（可选）     │
│    /kb → KBManager.list（按 allowlist 过滤）                 │
│    /admin/cache/clear → QueryCache.clear                     │
│    /health, /ready → 豁免鉴权                                │
└────────────────────────────────────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────────────────────┐
│ AppState (M2 升级: 单 KB → 多 KB)                          │
│   kbs: dict[str, GraphState]  ← 核心变化                  │
│   rebuild_locks: dict[str, Lock]  ← 每个 KB 独立           │
│   rebuild_tasks: dict[task_id, RebuildTask]                │
│   embedder_ready: bool                                     │
│   is_shutting_down: bool                                   │
│   auth_store: AuthStore                                    │
│   rate_limiter: RateLimitStore                             │
│   query_cache: QueryCache                                  │
└────────────────────────────────────────────────────────────┘
```

**改动清单**：

| 模块 | 类型 | 摘要 |
|------|------|------|
| `pyproject.toml` | edit | 无新依赖（都用 stdlib） |
| `src/tagmemorag/auth/base.py` | new | `AuthStore` ABC + `ApiKey` dataclass |
| `src/tagmemorag/auth/config_store.py` | new | `ConfigAuthStore` 实现 |
| `src/tagmemorag/auth/dependencies.py` | new | FastAPI `Depends`：`require_key / require_scope / require_kb_access` |
| `src/tagmemorag/rate_limit/base.py` | new | `RateLimitStore` ABC + `RateLimitResult` |
| `src/tagmemorag/rate_limit/memory_sliding.py` | new | 滑动窗口计数实现 |
| `src/tagmemorag/cache/base.py` | new | `QueryCache` ABC |
| `src/tagmemorag/cache/lru_ttl.py` | new | `LRUTTLCache` 实现 |
| `src/tagmemorag/kb_manager.py` | new | 多 KB 容器 + 按需加载 |
| `src/tagmemorag/config.py` | edit | 加 `AuthConfig / RateLimitConfig / CacheConfig / ApiKeyConfig` |
| `src/tagmemorag/state.py` | edit | `AppState` 从单 KB 升级为多 KB，重构 `start_rebuild` 接受 kb_name |
| `src/tagmemorag/api.py` | edit | 中间件链、依赖注入、端点改造、新增 `/kb` 和 `/admin/cache/clear` |
| `src/tagmemorag/errors.py` | edit | 加 `UNAUTHORIZED / FORBIDDEN / RATE_LIMITED` |
| `src/tagmemorag/anchor.py` | edit | `add/delete` 后递增 `anchors_version` |
| `src/tagmemorag/storage/json_anchor.py` | edit | `anchors.json` schema 加 `version` 字段 |
| `src/tagmemorag/types.py` | edit | `GraphState.anchors_version: int = 0` |
| `config.yaml` | edit | 加 `auth / rate_limit / cache` 段 |
| `tests/unit/test_auth.py` | new | key 鉴权 + scope + kb_allowlist |
| `tests/unit/test_rate_limit.py` | new | 滑动窗口精度 + 并发 |
| `tests/unit/test_cache.py` | new | LRU/TTL/invalidate |
| `tests/unit/test_multi_kb.py` | new | 两个 KB 并存隔离 |
| `tests/integration/test_m2_e2e.py` | new | 端到端：鉴权→限流→缓存→多 KB |
| `README.md` | edit | Auth / 限流 / 多 KB / 缓存章节 |

---

## 2. 数据契约

### 2.1 `ApiKey`（auth/base.py）

```python
@dataclass(frozen=True)
class ApiKey:
    id: str                          # 日志可见，运维定义的稳定 label id
    label: str                       # 人类可读描述
    hash: str                        # "sha256:<hex>"
    kb_allowlist: tuple[str, ...]    # () 或 ("*",) 视为全允许
    scopes: frozenset[str]           # {"search", "rebuild", "anchor.write", "admin"}
    rate_limit_per_minute: int
    created_at: str | None = None    # ISO8601
    last_used_at: str | None = None  # Config backend can keep this in memory only
    revoked: bool = False

    def allows_kb(self, kb_name: str) -> bool:
        if "admin" in self.scopes:
            return True
        if not self.kb_allowlist or self.kb_allowlist == ("*",):
            return True
        return kb_name in self.kb_allowlist

    def has_scope(self, required: str) -> bool:
        if "admin" in self.scopes:
            return True
        return required in self.scopes
```

### 2.2 `AuthStore`（auth/base.py）

```python
class AuthStore(ABC):
    @abstractmethod
    def verify(self, plaintext_key: str) -> ApiKey | None:
        """Constant-time verify; return ApiKey on success, None otherwise."""

    @abstractmethod
    def list_keys(self) -> list[ApiKey]:
        """For /auth/keys admin listing (masked secrets)."""

    def touch_usage(self, key_id: str) -> None:
        """Optional: update last_used_at. Config backend can no-op."""
        pass
```

### 2.3 `RateLimitStore`（rate_limit/base.py）

```python
@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    reset_epoch: int         # Unix 时间戳
    retry_after_seconds: int # 0 if allowed

class RateLimitStore(ABC):
    @abstractmethod
    def check_and_incr(
        self,
        key_id: str,
        limit_per_minute: int,
        now: float | None = None,
    ) -> RateLimitResult: ...
```

### 2.4 `QueryCache`（cache/base.py）

```python
class QueryCache(ABC):
    @abstractmethod
    def get(self, cache_key: str) -> dict | None: ...
    @abstractmethod
    def set(self, cache_key: str, value: dict) -> None: ...
    @abstractmethod
    def clear(self, kb_name: str | None = None) -> int:
        """Return number of entries removed."""
```

### 2.5 `GraphState` 新字段

```python
@dataclass
class GraphState:
    ...  # M0/M1 已有
    anchors_version: int = 0      # M2 new
```

### 2.6 `AppState` 升级

```python
@dataclass
class AppState:
    kbs: dict[str, GraphState] = field(default_factory=dict)
    rebuild_locks: dict[str, threading.Lock] = field(default_factory=dict)
    rebuild_tasks: dict[str, RebuildTask] = field(default_factory=dict)
    embedder_ready: bool = False
    is_shutting_down: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # Managers injected at lifespan startup
    auth_store: AuthStore | None = None
    rate_limiter: RateLimitStore | None = None
    query_cache: QueryCache | None = None

    def get_kb(self, kb_name: str) -> GraphState:
        with self._lock:
            if kb_name not in self.kbs:
                raise KbNotLoadedError(kb_name)
            return self.kbs[kb_name]

    def swap_kb(self, kb_name: str, new_state: GraphState) -> None:
        with self._lock:
            self.kbs[kb_name] = new_state

    def list_kbs(self) -> list[str]:
        with self._lock:
            return list(self.kbs.keys())

    def _lock_for(self, kb_name: str) -> threading.Lock:
        with self._lock:
            if kb_name not in self.rebuild_locks:
                self.rebuild_locks[kb_name] = threading.Lock()
            return self.rebuild_locks[kb_name]
```

---

## 3. 配置扩展

### 3.1 `config.yaml` 新增段

```yaml
auth:
  enabled: true
  backend: config               # config | sqlite (post-v1)
  public_paths:                 # 豁免鉴权的路径
    - /health
    - /ready
    - /docs
    - /redoc
    - /openapi.json
  global_max_rate_limit_per_minute: 1000   # 兜底
  keys:
    - id: "cs-system-a"
      hash: "sha256:abc123..."
      label: "客服系统 A"
      kb_allowlist: ["product-a", "product-b"]
      scopes: ["search"]
      rate_limit_per_minute: 200

    - id: "cs-admin"
      hash: "sha256:def456..."
      label: "运维"
      kb_allowlist: []          # [] 或 ["*"] 都表示全允许
      scopes: ["admin"]
      rate_limit_per_minute: 1000

rate_limit:
  enabled: true
  default_per_minute: 60        # ApiKey 没定义时兜底
  window_seconds: 60

cache:
  enabled: true
  max_entries: 10000
  ttl_seconds: 3600
```

### 3.2 环境变量

`auth.keys` 这种数组字段 **不用** env 覆盖（pydantic-settings 的嵌套 env 对数组支持弱，运维直接改 YAML 即可）。其他标量都可以：

```
TAGMEMORAG__AUTH__ENABLED=false
TAGMEMORAG__RATE_LIMIT__DEFAULT_PER_MINUTE=120
TAGMEMORAG__CACHE__MAX_ENTRIES=20000
TAGMEMORAG__CACHE__TTL_SECONDS=1800
```

---

## 4. 中间件链与依赖注入

### 4.1 执行顺序（从外到内）

```
Trace Middleware (M1)           → 生成/注入 trace_id
   │
   ▼
(HTTPBearer Dependency)          → 提取 Authorization header
   │
   ▼
require_key Dependency           → AuthStore.verify → ApiKey 或 401
   │  (public_paths 跳过)
   ▼
require_scope(scope_name)        → ApiKey.has_scope → 403 或 继续
   │  (每个端点声明需要的 scope)
   ▼
require_kb_access(kb_name)       → ApiKey.allows_kb → 403 或 继续
   │  (仅 kb_name 入参的端点)
   ▼
rate_limit Dependency            → RateLimitStore.check_and_incr → 429 或 继续
   │
   ▼
Endpoint handler
   │  (handler 内部)
   ▼
(缓存检查：仅 /search)
```

### 4.2 依赖函数签名

```python
# auth/dependencies.py
from fastapi import Depends, Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer_scheme = HTTPBearer(auto_error=False)

def require_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> ApiKey:
    settings = request.app.state.settings
    if not settings.auth.enabled:
        return _anonymous_key()
    if request.url.path in settings.auth.public_paths:
        return _anonymous_key()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ServiceError(ErrorCode.UNAUTHORIZED, "Missing or invalid Authorization.")
    api_key = request.app.state.app_state.auth_store.verify(credentials.credentials)
    if api_key is None:
        raise ServiceError(ErrorCode.UNAUTHORIZED, "Invalid API key.")
    if api_key.revoked:
        raise ServiceError(ErrorCode.UNAUTHORIZED, "Invalid API key.")
    # bind to contextvars for logging
    bind_contextvars(api_key_id=api_key.id)
    return api_key

def require_scope(scope: str):
    def _check(api_key: ApiKey = Depends(require_key)) -> ApiKey:
        if not api_key.has_scope(scope):
            raise ServiceError(
                ErrorCode.FORBIDDEN,
                f"Missing required scope.",
                {"required_scope": scope, "api_key_id": api_key.id},
            )
        return api_key
    return _check

def require_kb_access(kb_name_getter=lambda r: r.kb_name):
    def _check(request_body, api_key: ApiKey = Depends(require_key)) -> ApiKey:
        kb = kb_name_getter(request_body)
        if not api_key.allows_kb(kb):
            raise ServiceError(
                ErrorCode.FORBIDDEN,
                "kb_name not allowed for this API key.",
                {"kb_name": kb, "allowed": list(api_key.kb_allowlist), "api_key_id": api_key.id},
            )
        return api_key
    return _check

def rate_limit_dep(
    request: Request,
    api_key: ApiKey = Depends(require_key),
) -> None:
    settings = request.app.state.settings
    if not settings.rate_limit.enabled:
        return
    limiter = request.app.state.app_state.rate_limiter
    limit = api_key.rate_limit_per_minute or settings.rate_limit.default_per_minute
    limit = min(limit, settings.auth.global_max_rate_limit_per_minute)
    result = limiter.check_and_incr(api_key.id, limit)
    # 把 result 存入 request.state 给 response 中间件读
    request.state.rate_limit = result
    if not result.allowed:
        raise ServiceError(
            ErrorCode.RATE_LIMITED,
            "Rate limit exceeded.",
            {"limit": limit, "retry_after_seconds": result.retry_after_seconds},
        )
```

### 4.3 端点装配示例

```python
# api.py
@app.post("/search")
def search(
    request: SearchRequest,
    http: Request,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    # kb 访问检查（单独做，因为 kb_name 在 body 里）
    if not api_key.allows_kb(request.kb_name):
        raise ServiceError(ErrorCode.FORBIDDEN, ...)
    ...

@app.post("/rebuild", status_code=202)
def rebuild(
    request: RebuildRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    if not api_key.allows_kb(request.kb_name):
        raise ServiceError(ErrorCode.FORBIDDEN, ...)
    ...

@app.get("/kb")
def list_kb(api_key: ApiKey = Depends(require_scope("search"))):
    all_kbs = app_state.list_kbs()
    visible = [k for k in all_kbs if api_key.allows_kb(k)]
    return {"kbs": [graph_info_for(k) for k in visible]}

@app.post("/admin/cache/clear")
def clear_cache(
    request: CacheClearRequest,
    api_key: ApiKey = Depends(require_scope("admin")),
):
    cleared = app_state.query_cache.clear(request.kb_name)
    return {"cleared_count": cleared}
```

### 4.4 Response header 注入（限流）

在 trace_middleware 之后（或另起一个 response middleware）：

```python
@app.middleware("http")
async def rate_limit_headers(request: Request, call_next):
    response = await call_next(request)
    rl = getattr(request.state, "rate_limit", None)
    if rl is not None:
        response.headers["X-RateLimit-Limit"] = str(rl.limit)
        response.headers["X-RateLimit-Remaining"] = str(rl.remaining)
        response.headers["X-RateLimit-Reset"] = str(rl.reset_epoch)
        if not rl.allowed:
            response.headers["Retry-After"] = str(rl.retry_after_seconds)
    return response
```

---

## 5. 鉴权实现（ConfigAuthStore）

```python
# auth/config_store.py
import hashlib, hmac
from typing import Iterable

class ConfigAuthStore(AuthStore):
    def __init__(self, keys: Iterable[ApiKey]):
        # index by first 8 hex of hash for O(1) lookup hint
        self._keys = list(keys)
        self._by_hash = {k.hash: k for k in self._keys if not k.revoked}

    def verify(self, plaintext_key: str) -> ApiKey | None:
        computed = "sha256:" + hashlib.sha256(plaintext_key.encode()).hexdigest()
        # constant-time compare all candidate hashes to prevent timing enumeration
        matched: ApiKey | None = None
        for stored_hash, api_key in self._by_hash.items():
            if hmac.compare_digest(computed, stored_hash):
                matched = api_key
                # do not early-return — keep timing constant
        return matched

    def list_keys(self) -> list[ApiKey]:
        return list(self._keys)
```

**注意**：虽然 `self._by_hash` 是 dict lookup 理论上更快，但为了防止 timing attack，循环遍历 + `hmac.compare_digest` 是正确的做法。key 数量 <100，开销可忽略。

**哈希格式**：`"sha256:" + hex`，前缀将来可以扩展为 `"argon2id:..."`（如果以后加强 KDF）。

**秘钥生成工具**（CLI）：

```bash
python -m tagmemorag auth generate-key --id cs-system-a --scopes search --kb product-a,product-b --rate 200
# Output (运维复制到 config.yaml):
#   id: cs-system-a
#   hash: sha256:abc123...
#   label: ""
#   kb_allowlist: [product-a, product-b]
#   scopes: [search]
#   rate_limit_per_minute: 200
#
# Give this to the client:
#   tmr_live_K3xR2pQ...
```

---

## 6. 限流实现（InMemorySlidingWindowStore）

### 6.1 算法（滑动窗口计数）

```
当前时刻 t 落在当前窗口 [window_start, window_start + 60s)
offset_fraction = (t - window_start) / 60

prev_count = 上一分钟窗口的总计数
curr_count = 当前窗口已经计数

approx_used = prev_count * (1 - offset_fraction) + curr_count

if approx_used >= limit:
    deny
else:
    curr_count += 1
    allow
```

### 6.2 代码骨架

```python
# rate_limit/memory_sliding.py
import threading, time

class InMemorySlidingWindowStore(RateLimitStore):
    def __init__(self, window_seconds: int = 60, now_fn=time.time):
        self._window = window_seconds
        self._now = now_fn
        self._state: dict[str, tuple[int, int, int]] = {}  # key -> (window_start, curr, prev)
        self._lock = threading.Lock()

    def check_and_incr(self, key_id: str, limit_per_minute: int, now: float | None = None) -> RateLimitResult:
        if limit_per_minute <= 0:
            return RateLimitResult(False, 0, limit_per_minute, 0, self._window)
        t = now if now is not None else self._now()
        with self._lock:
            ws, curr, prev = self._state.get(key_id, (int(t // self._window * self._window), 0, 0))
            # 推进窗口
            while t >= ws + self._window:
                ws += self._window
                prev = curr
                curr = 0
            offset = (t - ws) / self._window
            approx = prev * (1 - offset) + curr
            if approx >= limit_per_minute:
                reset = ws + self._window
                retry = max(1, int(reset - t))
                self._state[key_id] = (ws, curr, prev)
                return RateLimitResult(False, 0, limit_per_minute, int(reset), retry)
            curr += 1
            self._state[key_id] = (ws, curr, prev)
            remaining = max(0, limit_per_minute - int(approx) - 1)
            return RateLimitResult(True, remaining, limit_per_minute, int(ws + self._window), 0)
```

### 6.3 测试要点

- 固定 `now_fn` 注入，测试完全不用 `sleep()`
- 验证 100 次以内全 allow、第 101 次 deny
- 跨窗口切换时旧计数平滑衰减
- 多线程下（`threading.Thread` ×10 各自打 10 次）总 allowed 数稳定等于 limit
- 不同 key_id 独立

---

## 7. 缓存实现（LRUTTLCache）

### 7.1 数据结构

标准 OrderedDict 实现 LRU + 每个 entry 存 `(value, expiry_epoch)`。

```python
# cache/lru_ttl.py
from collections import OrderedDict
import threading, time

class LRUTTLCache(QueryCache):
    def __init__(self, max_entries: int, ttl_seconds: int, now_fn=time.time):
        self._max = max_entries
        self._ttl = ttl_seconds
        self._now = now_fn
        self._data: OrderedDict[str, tuple[dict, float, str]] = OrderedDict()  # key -> (value, expiry, kb_name)
        self._lock = threading.Lock()

    def get(self, cache_key: str) -> dict | None:
        with self._lock:
            entry = self._data.get(cache_key)
            if entry is None:
                return None
            value, expiry, _kb = entry
            if self._now() >= expiry:
                self._data.pop(cache_key, None)
                return None
            self._data.move_to_end(cache_key)
            return value

    def set(self, cache_key: str, value: dict, kb_name: str = "") -> None:
        with self._lock:
            expiry = self._now() + self._ttl
            if cache_key in self._data:
                self._data.move_to_end(cache_key)
            self._data[cache_key] = (value, expiry, kb_name)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self, kb_name: str | None = None) -> int:
        with self._lock:
            if kb_name is None:
                n = len(self._data)
                self._data.clear()
                return n
            keys_to_remove = [k for k, (_, _, kb) in self._data.items() if kb == kb_name]
            for k in keys_to_remove:
                del self._data[k]
            return len(keys_to_remove)
```

### 7.2 Cache key 生成

```python
# api.py
import hashlib

def _normalize_question(q: str) -> str:
    return " ".join(q.strip().split())

def _compute_cache_key(req: SearchRequest, state: GraphState, settings: Settings) -> str:
    parts = [
        req.kb_name,
        state.build_id,
        str(state.anchors_version),
        _normalize_question(req.question),
        str(req.top_k or settings.search.top_k),
        str(req.source_k or settings.search.source_k),
        str(req.steps if req.steps is not None else settings.search.steps),
        str(req.decay if req.decay is not None else settings.search.decay),
        str(req.amplitude_cutoff if req.amplitude_cutoff is not None else settings.search.amplitude_cutoff),
        req.aggregate or settings.search.aggregate,
    ]
    raw = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
```

### 7.3 `/search` 内部流程

```python
@app.post("/search")
def search(...):
    state = app_state.get_kb(request.kb_name)
    cache = app_state.query_cache
    cache_key = _compute_cache_key(request, state, settings) if cache else None

    if cache_key and (cached := cache.get(cache_key)):
        return {
            **cached,
            "trace_id": request.state.trace_id,         # 新 trace_id
            "search_time_ms": round((time.perf_counter() - t0) * 1000, 3),
            "cache": "hit",
        }

    # miss → 走 embedder + wave_search
    results = wave_search(...)
    payload = {"build_id": state.build_id, "results": [...], "kb_name": state.kb_name, "cache": "miss"}

    if cache_key:
        cache.set(cache_key, {**payload, "search_time_ms": 0}, kb_name=request.kb_name)  # 缓存体不含 trace_id / 实际耗时

    return {**payload, "trace_id": request.state.trace_id, "search_time_ms": ...}
```

---

## 8. 多 KB 管理（kb_manager.py）

### 8.1 加载策略

- **启动时**：扫描 `data/` 下所有子目录，对每个含 `meta.json` 的目录调用 `load_kb(kb_name, cfg)` 加载到 `app_state.kbs`
- **rebuild 时**：从 `app_state.kbs.get(kb_name)` 取同名 KB 的旧状态作为 `old_state`，`build_kb` 成功后 `app_state.swap_kb(kb_name, new_state)`；不能把其他 KB 的状态传入，避免锚点跨 KB 串联
- **kb_name 白名单**：`app_state.list_kbs()` 返回所有已加载 KB；权限过滤在 handler 做

### 8.2 每 KB 独立的 rebuild lock

```python
def start_rebuild(self, docs_dir, kb_name, cfg, embedder) -> RebuildTask:
    with self._lock:
        if self.is_shutting_down:
            raise ShuttingDownError()
    lock = self._lock_for(kb_name)
    if not lock.acquire(blocking=False):
        raise RebuildInProgressError(...)
    # 启动 worker thread
    ...
```

**并发语义**：
- KB A 在 rebuild 不影响 KB B 接收新 rebuild 请求
- 同一 KB 的并发 rebuild 请求立即 409 `REBUILD_IN_PROGRESS`
- Shutdown 时 `await` 所有 kb 的 rebuild lock 释放

### 8.3 `GET /kb` 响应

```python
{
    "kbs": [
        {"kb_name": "product-a", "build_id": "...", "node_count": 142, "anchors_version": 3, "status": "ready"},
        {"kb_name": "product-b", "build_id": "...", "node_count": 89, "anchors_version": 0, "status": "rebuilding"},
    ]
}
```

`status`: `ready | rebuilding | loading_failed`

---

## 9. 错误码与 HTTP 映射（全量）

| ErrorCode | HTTP | 来源 |
|-----------|------|------|
| KB_NOT_LOADED | 404 | M0 |
| ANCHOR_NOT_FOUND | 404 | M0 |
| REBUILD_IN_PROGRESS | 409 | M0 |
| STORAGE_SCHEMA_MISMATCH | 409 | M0 |
| INVALID_REQUEST / INVALID_INPUT / INVALID_CONFIG | 400 | M0 |
| STORAGE_LOAD_FAILED / REBUILD_FAILED | 500 | M0 |
| INTERNAL | 500 | M0 |
| SHUTTING_DOWN | 503 | M1 |
| EMBEDDING_FAILED | 502 | M1 |
| **UNAUTHORIZED** | **401** | **M2 new** |
| **FORBIDDEN** | **403** | **M2 new** |
| **RATE_LIMITED** | **429** | **M2 new** |

所有错误响应统一 `{"code", "message", "detail"}` 格式（M0 已确定）。

---

## 10. Lifespan 启动/关闭（M1 基础上扩展）

### 10.1 startup

```
1. configure_logging
2. logger.info("service_starting")
3. 初始化 embedder（M1）
4. warm-up encode（M1）
5. # M2 new: 装配各个 store
   auth_store = ConfigAuthStore.from_settings(settings.auth)
   rate_limiter = InMemorySlidingWindowStore(settings.rate_limit.window_seconds)
   query_cache = LRUTTLCache(settings.cache.max_entries, settings.cache.ttl_seconds) if settings.cache.enabled else None
   app_state.auth_store = auth_store
   app_state.rate_limiter = rate_limiter
   app_state.query_cache = query_cache
   app.state.settings = settings
   app.state.app_state = app_state
6. # M2 new: 扫描 data/ 加载所有 KB
   for kb_dir in (Path(settings.storage.data_dir)).iterdir():
       if (kb_dir / "meta.json").exists():
           try:
               app_state.swap_kb(kb_dir.name, load_kb(kb_dir.name, settings))
               logger.info("kb_loaded", kb_name=kb_dir.name)
           except KbNotLoadedError:
               logger.warning("kb_load_skipped", kb_name=kb_dir.name)
7. logger.info("service_ready", kb_count=len(app_state.kbs))
8. yield
```

### 10.2 shutdown

和 M1 一致，但要等所有 kb 的 rebuild lock：

```
1. begin_shutdown()
2. for kb_name in app_state.list_kbs():
     await asyncio.to_thread(app_state._lock_for(kb_name).acquire)
     app_state._lock_for(kb_name).release()
3. logger.info("shutdown_complete")
```

---

## 11. README 新增内容（草稿）

### API 认证

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"question": "蒸汽很小", "kb_name": "product-a"}'
```

### 生成 API key

```bash
python -m tagmemorag auth generate-key --id cs-system-a --scopes search --kb product-a --rate 200
```

### 多 KB 配置

每个 KB 在 `data/{kb_name}/` 下独立存储。首次启动时扫描并加载所有 KB。

```bash
# 构建 product-a
python -m tagmemorag build --docs docs/product-a --kb product-a
# 构建 product-b
python -m tagmemorag build --docs docs/product-b --kb product-b
```

### 限流响应头

```
HTTP/1.1 200 OK
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 178
X-RateLimit-Reset: 1715500800
```

超限：

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1715500800
Content-Type: application/json

{"code": "RATE_LIMITED", "message": "Rate limit exceeded.", "detail": {...}}
```

### 缓存清理

```bash
# 清所有 KB 缓存
curl -X POST http://127.0.0.1:8000/admin/cache/clear \
  -H "Authorization: Bearer tmr_live_admin..." \
  -d '{}'

# 只清某个 KB
curl -X POST http://127.0.0.1:8000/admin/cache/clear \
  -H "Authorization: Bearer tmr_live_admin..." \
  -d '{"kb_name": "product-a"}'
```

---

## 12. 测试策略

| 测试 | 文件 | 范围 |
|------|------|------|
| AuthStore verify 正确/错误/revoked | test_auth.py | ConfigAuthStore.verify |
| 常数时间对比无短路 | test_auth.py | hmac.compare_digest 路径 |
| `require_key` 缺失/无效/过期 → 401 | test_auth.py | 依赖链 |
| `require_scope` 不足 → 403 | test_auth.py | |
| `require_kb_access` 拒绝 → 403 | test_auth.py | |
| 公开路径豁免 | test_auth.py | /health /ready |
| admin scope 跨 KB | test_auth.py | |
| 限流：允许 / 边界 / 拒绝 / 跨窗口恢复 | test_rate_limit.py | mock now_fn |
| 限流：不同 key 独立 | test_rate_limit.py | |
| 限流：并发线程下总计数一致 | test_rate_limit.py | |
| 响应头 X-RateLimit-* | test_rate_limit.py | TestClient |
| 缓存 set/get/miss/ttl expiry | test_cache.py | mock now_fn |
| LRU 淘汰最旧 | test_cache.py | |
| clear(kb_name) 只清指定 | test_cache.py | |
| cache key 对所有参数敏感 | test_cache.py | |
| rebuild 后同一 query miss（新 build_id） | test_cache.py | |
| 锚点变更后 miss（anchors_version++） | test_cache.py | |
| 多 KB：两 KB 独立并存 | test_multi_kb.py | 启动时扫描加载 |
| 多 KB：一个 rebuild 不影响另一个 | test_multi_kb.py | |
| 多 KB：admin 可见所有，普通 key 只见 allowlist | test_multi_kb.py | |
| E2E：鉴权→限流→缓存→多 KB | test_m2_e2e.py | TestClient |

---

## 13. 字段可追溯性

| PRD 决策 | design 对应段 |
|----------|--------------|
| config 存 hash + AuthStore ABC | §2.1-2.2 + §5 |
| `Authorization: Bearer` + HTTPBearer | §4.2 `require_key` |
| 滑动窗口 + InMemory + RateLimitStore ABC | §2.3 + §6 |
| kb 白名单 + scopes | §2.1 `ApiKey.allows_kb/has_scope` + §4.2 |
| cache key = kb+build_id+anchors_version+参数 | §7.2 |
| 被动淘汰 + admin 清理端点 | §7.1 + §4.3 |
| 新增错误码 401/403/429 | §9 |
| 多 KB 隔离（AppState.kbs） | §2.6 + §8 |
| 启动时扫描 data/ | §10.1 |

---

## 14. 不做什么

- 多副本协调 / leader election → post-v1
- Prometheus / OTel → M4
- DB 鉴权 / 动态 key CRUD → post-v1（接口已预留）
- Redis 限流 / 缓存 → post-v1（接口已预留）
- 更细粒度 RBAC（比如按 anchor label、具体端点或操作对象授权） → post-v1；M2 仅实现 `search / rebuild / anchor.write / admin` 四类 scope
