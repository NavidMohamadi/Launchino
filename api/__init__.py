"""FastAPI service layer for the SHEXON Talent Fit MVP.

This package is a thin HTTP/Postgres shell around the deterministic matching
library in ``src/`` (schemas, activation, comparators, match_engine). It does
not reimplement or alter that logic; it loads it, persists its inputs and
outputs in PostgreSQL (schema defined in ``src/database_schema.sql``), and
exposes it over REST.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

REPO_ROOT = _REPO_ROOT
