"""Confirms an unhandled exception in a route never leaks internal details
(exception message, type, stack trace) to the HTTP client -- only FastAPI/
Starlette's generic 500 body. No debug=True and no custom exception handler
exist anywhere in api/main.py (confirmed by grep during the security-hardening
pass); this test asserts that stays true rather than relying on re-reading
the code each time.

raise_server_exceptions=False is required here: TestClient's default
behavior re-raises the exception into the test process (useful for
debugging, but it means the test would see the real exception instead of
what an actual HTTP client receives) -- False makes it behave like a real
deployed server, converting the unhandled exception into whatever response
the client would really get.

Overrides the get_connection dependency (rather than patching business
logic like verify_password) so the failure is unconditional -- every route
calls conn.execute() as its first real action regardless of whether the
submitted email/data exists, so this doesn't depend on any specific seed
data being present.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.database import get_connection  # noqa: E402
from api.main import app  # noqa: E402

SECRET_MARKER = "SECRET_INTERNAL_DETAIL_ArbitraryDbPathOrTraceback"


def _broken_get_connection():
    raise RuntimeError(SECRET_MARKER)
    yield  # pragma: no cover -- unreachable, but keeps this a generator like the real dependency


def test_unhandled_exception_does_not_leak_internal_details():
    client = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides[get_connection] = _broken_get_connection
    try:
        response = client.post(
            "/candidates/login",
            json={"email": "error-handling-test@example.com", "password": "irrelevant123"},
        )
    finally:
        app.dependency_overrides.pop(get_connection, None)

    assert response.status_code == 500
    assert SECRET_MARKER not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
    assert response.text == "Internal Server Error"
