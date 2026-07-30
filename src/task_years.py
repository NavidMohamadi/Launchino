"""Computes TASK-YEARS from TASK-EXPERIENCE's own job entries -- TASK-YEARS
is never a direct candidate answer (see data/fit_dictionary_starter.json's
own evidence_rule for it, and PROJECT_NOTES.md's Phase 4 entry). Pure
date-math, no DB/HTTP dependency -- api/routers/candidates.py's
submit_candidate_survey is the only caller, wiring this in whenever a
submission includes a TASK-EXPERIENCE answer.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional


def compute_total_years_experience(jobs: List[Dict[str, Any]], *, as_of: Optional[date] = None) -> int:
    """Whole years, floored, from the union of each job's [start_date, end_date)
    span -- overlapping/concurrent jobs are merged before summing so two
    part-time roles held at the same time don't double-count that stretch of
    time. Floors rather than rounds: 1.9 computed years reports as 1, not 2,
    matching this project's general "don't overstate what's evidenced"
    posture. Entries with a missing/unparseable start_date, or an end_date
    before start_date, are skipped rather than raising -- this runs
    automatically on every survey submission, so it must degrade gracefully
    on partial/malformed entries rather than blocking the whole submission.
    """
    as_of = as_of or date.today()
    intervals = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        start_raw = job.get("start_date")
        if not start_raw:
            continue
        try:
            start = date.fromisoformat(start_raw)
        except (TypeError, ValueError):
            continue
        if job.get("current"):
            end = as_of
        else:
            end_raw = job.get("end_date")
            if not end_raw:
                continue
            try:
                end = date.fromisoformat(end_raw)
            except (TypeError, ValueError):
                continue
        if end <= start:
            continue
        intervals.append((start, end))

    if not intervals:
        return 0

    intervals.sort(key=lambda span: span[0])
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    total_days = sum((end - start).days for start, end in merged)
    return int(total_days // 365.25)
