from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from structlog.contextvars import bind_contextvars

from tagmemorag.errors import ForbiddenError, RateLimitedError, UnauthorizedError
from tagmemorag.observability.metrics import get_metrics

from .base import ApiKey, anonymous_key


bearer_scheme = HTTPBearer(auto_error=False)


def require_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> ApiKey:
    settings = request.app.state.settings
    if not settings.auth.enabled or request.url.path in settings.auth.public_paths:
        key = anonymous_key()
        bind_contextvars(api_key_id=key.id)
        return key
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError()
    store = request.app.state.app_state.auth_store
    api_key = store.verify(credentials.credentials) if store is not None else None
    if api_key is None or api_key.revoked:
        raise UnauthorizedError("Invalid API key.")
    store.touch_usage(api_key.id)
    bind_contextvars(api_key_id=api_key.id)
    return api_key


def require_scope(scope: str):
    def _check(api_key: ApiKey = Depends(require_key)) -> ApiKey:
        if not api_key.has_scope(scope):
            raise ForbiddenError("Missing required scope.", {"required_scope": scope, "api_key_id": api_key.id})
        return api_key

    return _check


def ensure_kb_access(api_key: ApiKey, kb_name: str) -> None:
    if not api_key.allows_kb(kb_name):
        raise ForbiddenError(
            "kb_name not allowed for this API key.",
            {"kb_name": kb_name, "allowed": list(api_key.kb_allowlist), "api_key_id": api_key.id},
        )


def rate_limit_dep(request: Request, api_key: ApiKey = Depends(require_key)) -> None:
    settings = request.app.state.settings
    if not settings.rate_limit.enabled:
        return
    limiter = request.app.state.app_state.rate_limiter
    if limiter is None:
        return
    configured = (
        api_key.rate_limit_per_minute
        if api_key.rate_limit_per_minute is not None
        else settings.rate_limit.default_per_minute
    )
    limit = min(configured, settings.auth.global_max_rate_limit_per_minute)
    result = limiter.check_and_incr(api_key.id, limit)
    request.state.rate_limit = result
    get_metrics().record_rate_limit(outcome="allowed" if result.allowed else "limited")
    if not result.allowed:
        raise RateLimitedError({"limit": result.limit, "retry_after_seconds": result.retry_after_seconds})
