from __future__ import annotations

from typing import Dict

import httpx

from .base import HttpResponse


class HttpxClient:
    def __init__(self, user_agent: str = "SHEXON-JobDiscovery/2.0"):
        self.user_agent = user_agent

    def get(self, url: str, *, headers: Dict[str, str] | None = None, timeout: float = 20.0) -> HttpResponse:
        merged = {"User-Agent": self.user_agent, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
        if headers:
            merged.update(headers)
        response = httpx.get(url, headers=merged, timeout=timeout, follow_redirects=True)
        json_data = None
        if "json" in response.headers.get("content-type", "").lower():
            json_data = response.json()
        return HttpResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            text=response.text,
            json_data=json_data,
        )
