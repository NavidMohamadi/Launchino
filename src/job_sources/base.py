from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Protocol

from source_schemas import RawVacancyRecord


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Dict[str, str]
    text: str
    json_data: Any | None = None

    def json(self):
        if self.json_data is None:
            raise ValueError("No parsed JSON was supplied")
        return self.json_data


class HttpClient(Protocol):
    def get(self, url: str, *, headers: Dict[str, str] | None = None, timeout: float = 20.0) -> HttpResponse: ...


class JobSourceAdapter(ABC):
    source_id: str

    @abstractmethod
    def fetch(self, identifier: str, client: HttpClient) -> list[RawVacancyRecord]:
        raise NotImplementedError
