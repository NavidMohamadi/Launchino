"""Shared slowapi Limiter instance, in its own module so both api/main.py
(middleware/exception-handler wiring) and individual routers (per-route
@limiter.limit(...) decorators) can import it without a circular import.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter


def client_ip(request: Request) -> str:
    """Rate-limit key. Render/Cloudflare sit in front of this app in
    production, so request.client.host is the proxy's address, not the real
    caller's -- X-Forwarded-For's first entry is the original client for a
    single well-behaved proxy hop. Falls back to request.client.host for
    direct local-dev access, where no such header is set."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip)
