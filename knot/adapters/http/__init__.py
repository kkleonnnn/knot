"""knot.adapters.http — Generic HTTP executor (v0.6.1.4 OSS-friendly)

OVERRIDE #3 (2026-05-24)：撤回守护者 §IV P2-2「不做通用 HTTP 配置化框架」红线。
理由：KNOT 是 OSS 项目；endpoint 完全 catalog-driven，部署方 admin UI 配置任何 API。

调用契约：
    from knot.adapters.http import execute, HTTPEndpointSpec, HTTPAdapterError
    rows = execute(spec, params)   # spec 来自 catalog.tables.<name>.http_spec

安全模型（多层防御替代 PR review）：
- env KNOT_HTTP_ALLOWED_HOSTS allowlist 守护 URL host
- admin role + audit log + 2FA
- rate limit per endpoint pattern
"""
from knot.adapters.http.base import (  # noqa: F401
    HTTPAdapterError,
    HTTPAuthError,
    HTTPEndpointSpec,
    HTTPTimeout,
    HTTPUnavailable,
)
from knot.adapters.http.executor import execute  # noqa: F401
from knot.adapters.http.url_allowlist import (  # noqa: F401
    check_url_allowed,
    get_allowed_hosts,
    is_url_allowed,
)
