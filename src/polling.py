from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List

from source_schemas import CompanyJobSource


def due_sources(sources: Iterable[CompanyJobSource], *, now: datetime | None = None) -> List[CompanyJobSource]:
    now = now or datetime.now(timezone.utc)
    output = []
    for source in sources:
        if not source.enabled:
            continue
        if source.next_poll_at is None or source.next_poll_at <= now:
            output.append(source)
    return sorted(output, key=lambda s: (s.next_poll_at or datetime.min.replace(tzinfo=timezone.utc), s.source_record_id))


def mark_polled(source: CompanyJobSource, *, polled_at: datetime | None = None) -> CompanyJobSource:
    polled_at = polled_at or datetime.now(timezone.utc)
    updated = source.model_copy(deep=True)
    updated.last_polled_at = polled_at
    updated.next_poll_at = polled_at + timedelta(minutes=updated.polling_interval_minutes)
    return updated
