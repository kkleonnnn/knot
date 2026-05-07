"""tests/api/ 复用 tests/integration/conftest.py 的 client / admin_token / auth_headers fixtures。"""
from tests.integration.conftest import (  # noqa: F401
    admin_token,
    auth_headers,
    client,
)
