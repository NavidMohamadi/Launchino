"""Disables slowapi rate limiting for the whole test session.

api/rate_limit.py's Limiter uses in-memory storage keyed by client IP, shared
across every test module in this single pytest process (all real-DB tests
share one TestClient "IP"). Registration is capped at 5/hour in production
(api/routers/candidates.py) -- a real, correct limit for real traffic, but
enough test files call POST /candidates that the shared bucket overflows
partway through a full-suite run, failing later tests with 429s that have
nothing to do with what they're actually testing. No test in this suite
exercises rate-limiting behavior itself (confirmed: no test asserts on a 429
response), so disabling it here doesn't remove real coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from api.rate_limit import limiter  # noqa: E402

limiter.enabled = False
