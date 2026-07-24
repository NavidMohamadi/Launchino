"""Manually-triggered job discovery polling: adapters -> dedup -> merge -> lifecycle.

This module is never imported by api/main.py and registers no scheduler,
cron, or background task of any kind. The only ways to run it are:

    python -m api.job_discovery_scheduler --validate-only
    python -m api.job_discovery_scheduler --run-once

Company/board list: data/company_registry_live.json. Adding or removing a
board is a one-line edit to that file's "boards" array -- no code change,
for the four sources currently registered (greenhouse/lever/ashby, plus the
one-off avular_careers_html -- see PROJECT_NOTES.md: that one is a hand-built,
single-site parser with no stable contract, not a generalized "custom HTML
company" capability; adding a fifth non-ATS company means repeating that
whole review process, not just adding a JSON entry).

Trust boundary note (mirrors the one on POST /vacancies/{id}/workshop): rows
this module writes get verification_status=source_verified (real scraped
provenance, not company-direct), computed by canonical_vacancy.py /
vacancy_merge.py exactly as it already does for the existing test suite --
this module doesn't invent a new trust level, it just runs the existing,
frozen ingestion logic for real and persists what it returns.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.engine import Connection

from company_registry import CompanyRegistry
from job_sources.ashby import AshbyAdapter
from job_sources.avular import AvularCareersAdapter
from job_sources.base import HttpClient, JobSourceAdapter
from job_sources.greenhouse import GreenhouseAdapter
from job_sources.http_client import HttpxClient
from job_sources.lever import LeverAdapter
from polling import due_sources, mark_polled
from source_policy import SourcePolicyRegistry
from source_schemas import (
    AcquisitionMethod, CompanyJobSource, CompanyRecord, VacancyIntakeSource, VacancyLifecycleStatus,
)
from vacancy_ingestion import VacancyIngestionService, VacancyRepository
from vacancy_lifecycle import mark_missing

from api import REPO_ROOT
from api.ingestion_store import (
    insert_poll_run, insert_provenance, insert_source_conflict, insert_snapshot_if_new,
    insert_vacancy_dedup_review, link_vacancy_snapshot, load_existing_profiles, seed_source_policy,
    upsert_company, upsert_company_job_source,
)
from api.vacancy_store import upsert_vacancy

# --- Config: adjust these, not the logic below, to retune the schedule. ---
POLL_INTERVAL_HOURS = 8  # requested range: 6-12 hours
RECENT_ENOUGH_WINDOW_DAYS = 14  # matches job_discovery_access.py's own backfill/campaign window
STALE_AFTER_POLLS = 2  # consecutive misses before lifecycle_status -> stale
CLOSE_AFTER_POLLS = 3  # consecutive misses before lifecycle_status -> closed ("a small number")

LIVE_REGISTRY_PATH = REPO_ROOT / "data" / "company_registry_live.json"
SOURCE_POLICY_PATH = REPO_ROOT / "data" / "source_registry.json"

ATS_TO_SOURCE_ID = {
    "greenhouse": "greenhouse_public_api",
    "lever": "lever_public_api",
    "ashby": "ashby_public_api",
    # One-off, not a generalized "custom HTML" category -- see PROJECT_NOTES.md.
    "avular": "avular_careers_html",
}
ATS_ADAPTERS: Dict[str, type[JobSourceAdapter]] = {
    "greenhouse_public_api": GreenhouseAdapter,
    "lever_public_api": LeverAdapter,
    "ashby_public_api": AshbyAdapter,
    "avular_careers_html": AvularCareersAdapter,
}
ATS_LISTING_URL = {
    "greenhouse": "https://boards.greenhouse.io/{token}",
    "lever": "https://jobs.lever.co/{token}",
    "ashby": "https://jobs.ashbyhq.com/{token}",
    # For avular, board_token in the registry file is the site's base URL
    # itself (AvularCareersAdapter.fetch treats its identifier as a base_url,
    # not a per-tenant token -- there's only ever one Avular).
    "avular": "{token}/careers",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "company"


def load_live_boards(path: Path = LIVE_REGISTRY_PATH) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("boards", [])


def _stable_uuid(*parts: str) -> str:
    """Deterministic per input, unlike uuid4() -- so the same board config
    gets the same company_id/source_record_id across repeated poll cycles
    (both columns are typed uuid in src/database_schema.sql, so a
    human-readable slug like "live-greenhouse" isn't valid there)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "shexon-job-discovery:" + ":".join(parts)))


def build_company_registry(boards: List[dict]) -> CompanyRegistry:
    companies: Dict[str, CompanyRecord] = {}
    sources: List[CompanyJobSource] = []
    for board in boards:
        name = board["name"]
        ats = board["ats"]
        if ats not in ATS_TO_SOURCE_ID:
            raise ValueError(
                f"Unsupported ats '{ats}' for board '{name}'. Only {sorted(ATS_TO_SOURCE_ID)} are approved "
                "(see data/source_registry.json); adding a new ATS type is out of scope for this module."
            )
        token = board["board_token"]
        company_id = _stable_uuid("company", name)
        companies[company_id] = CompanyRecord(
            company_id=company_id, legal_name=name, display_name=name,
            website_domain=board.get("domain", ""), active=True,
        )
        source_id = ATS_TO_SOURCE_ID[ats]
        sources.append(CompanyJobSource(
            source_record_id=_stable_uuid("source", ats, token),
            company_id=company_id, source_id=source_id,
            intake_source=VacancyIntakeSource.PUBLIC_ATS_API, acquisition_method=AcquisitionMethod.API,
            board_identifier=token, listing_url=ATS_LISTING_URL[ats].format(token=token),
            enabled=board.get("enabled", True), polling_interval_minutes=POLL_INTERVAL_HOURS * 60,
        ))
    return CompanyRegistry(companies, sources)


@dataclass
class BoardValidationResult:
    company_name: str
    source_id: str
    board_identifier: str
    status: str  # "ok" | "empty" | "error"
    job_count: int = 0
    error: Optional[str] = None


def validate_board(source: CompanyJobSource, company_name: str, client: HttpClient) -> BoardValidationResult:
    adapter_cls = ATS_ADAPTERS.get(source.source_id)
    if adapter_cls is None:
        return BoardValidationResult(company_name, source.source_id, source.board_identifier, "error", 0, "no adapter for this source_id")
    try:
        raws = adapter_cls().fetch(source.board_identifier, client)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any failure means "don't trust this board yet"
        return BoardValidationResult(company_name, source.source_id, source.board_identifier, "error", 0, str(exc))
    if not raws:
        return BoardValidationResult(company_name, source.source_id, source.board_identifier, "empty", 0, None)
    return BoardValidationResult(company_name, source.source_id, source.board_identifier, "ok", len(raws), None)


def validate_all_boards(registry: CompanyRegistry, client: Optional[HttpClient] = None) -> List[BoardValidationResult]:
    client = client or HttpxClient()
    return [
        validate_board(source, registry.companies[source.company_id].display_name, client)
        for source in registry.sources
    ]


@dataclass
class PollCycleReport:
    as_of: datetime
    boards_considered: int = 0
    boards_validated_ok: int = 0
    boards_skipped: int = 0
    board_validations: List[BoardValidationResult] = field(default_factory=list)
    vacancies_created: int = 0
    vacancies_updated: int = 0
    vacancies_unchanged_duplicate: int = 0
    vacancies_review_required: int = 0
    vacancies_marked_stale: int = 0
    vacancies_marked_closed: int = 0


def run_poll_cycle(
    conn: Connection, *, registry_path: Path = LIVE_REGISTRY_PATH, client: Optional[HttpClient] = None,
    as_of: Optional[datetime] = None,
) -> PollCycleReport:
    as_of = as_of or datetime.now(timezone.utc)
    client = client or HttpxClient()
    report = PollCycleReport(as_of=as_of)

    registry = build_company_registry(load_live_boards(registry_path))
    seed_source_policy(conn, SOURCE_POLICY_PATH)
    for company in registry.companies.values():
        upsert_company(conn, company)
    for source in registry.sources:
        upsert_company_job_source(conn, source)

    due = due_sources(registry.sources, now=as_of)
    report.boards_considered = len(due)

    validations = {
        source.source_record_id: validate_board(source, registry.companies[source.company_id].display_name, client)
        for source in due
    }
    report.board_validations = list(validations.values())
    valid_sources = [s for s in due if validations[s.source_record_id].status == "ok"]
    report.boards_validated_ok = len(valid_sources)
    report.boards_skipped = len(due) - len(valid_sources)

    policy_registry = SourcePolicyRegistry.from_json(SOURCE_POLICY_PATH)
    repository = VacancyRepository()
    for profile in load_existing_profiles(conn):
        repository.save_profile(profile)
    service = VacancyIngestionService(policy_registry=policy_registry, company_registry=registry, repository=repository)

    # Collected here, persisted at the end (after snapshot/vacancy upserts) so
    # vacancy_dedup_review's two foreign keys (incoming_snapshot_id, candidate_vacancy_id)
    # already exist by the time we insert.
    pending_dedup_reviews: List[dict] = []

    # Per-source breakdown for poll_run (see the loop near the end of this
    # function) -- report.vacancies_created/updated above are cycle-wide totals,
    # which isn't enough to tell which specific board a change came from.
    per_source_created: Dict[str, int] = {}
    per_source_updated: Dict[str, int] = {}

    for source in valid_sources:
        adapter_cls = ATS_ADAPTERS[source.source_id]
        raws = adapter_cls().fetch(source.board_identifier, client)
        company = registry.companies[source.company_id]

        seen_vacancy_ids = set()
        for raw in raws:
            # Adapters set company_name to the bare board token (they can't
            # know the "pretty" name); override with the registry's real
            # name/domain before ingesting, matching tests/test_vacancy_ingestion.py.
            raw.company_name = company.display_name
            raw.company_domain = company.website_domain or raw.company_domain
            outcome = service.ingest(raw)
            seen_vacancy_ids.add(outcome.profile.vacancy_id)
            if outcome.created:
                report.vacancies_created += 1
                per_source_created[source.source_record_id] = per_source_created.get(source.source_record_id, 0) + 1
            elif any(flag.startswith("possible_duplicate_needs_review") for flag in outcome.review_flags):
                report.vacancies_review_required += 1
                # review_flags is ["possible_duplicate_needs_review", <reason>] --
                # see vacancy_ingestion.py's review_required branch.
                reason = outcome.review_flags[1] if len(outcome.review_flags) > 1 else "possible duplicate"
                if outcome.snapshot_id and outcome.duplicate_of:
                    pending_dedup_reviews.append({
                        "incoming_snapshot_id": outcome.snapshot_id,
                        "candidate_vacancy_id": outcome.duplicate_of,
                        "decision_reason": reason,
                        "confidence": outcome.confidence,
                    })
            elif outcome.updated:
                report.vacancies_updated += 1
                per_source_updated[source.source_record_id] = per_source_updated.get(source.source_record_id, 0) + 1
            else:
                report.vacancies_unchanged_duplicate += 1

        # Vacancies previously tied to this exact source but not seen this cycle.
        for vacancy_id, profile in list(repository.profiles.items()):
            if profile.company_id != source.company_id or source.source_id not in profile.external_job_ids:
                continue
            if vacancy_id in seen_vacancy_ids:
                continue
            if profile.lifecycle_status in (VacancyLifecycleStatus.CLOSED, VacancyLifecycleStatus.ARCHIVED):
                continue
            updated_profile = mark_missing(
                profile, today=as_of.date(), observed_at=as_of,
                stale_after_polls=STALE_AFTER_POLLS, close_after_polls=CLOSE_AFTER_POLLS,
            )
            repository.save_profile(updated_profile)
            if updated_profile.lifecycle_status == VacancyLifecycleStatus.CLOSED and profile.lifecycle_status != VacancyLifecycleStatus.CLOSED:
                report.vacancies_marked_closed += 1
            elif updated_profile.lifecycle_status == VacancyLifecycleStatus.STALE and profile.lifecycle_status != VacancyLifecycleStatus.STALE:
                report.vacancies_marked_stale += 1

    # Mark every attempted (due) source as polled, whether or not it validated,
    # so a dead board doesn't get retried on the very next invocation.
    for source in due:
        upsert_company_job_source(conn, mark_polled(source, polled_at=as_of))

    # One poll_run row per due source, whether it validated or not -- this is
    # the only place "which boards are currently failing/empty" and "last
    # successful poll" can come from; company_job_source.last_polled_at alone
    # only means "attempted," not "succeeded" (see the loop above). No finer
    # start/complete timing exists in this single-pass validate+ingest model,
    # so both are stamped as_of.
    for source in due:
        validation = validations[source.source_record_id]
        insert_poll_run(
            conn, source_record_id=source.source_record_id, started_at=as_of, completed_at=as_of,
            status=validation.status, jobs_seen=validation.job_count,
            jobs_created=per_source_created.get(source.source_record_id, 0),
            jobs_updated=per_source_updated.get(source.source_record_id, 0),
            error_message=validation.error,
        )

    # Persist final in-memory state: vacancies, snapshots, links, provenance, conflicts.
    for snapshot in repository.snapshots.values():
        insert_snapshot_if_new(conn, snapshot)
    for profile in repository.profiles.values():
        upsert_vacancy(conn, profile)
        for index, snapshot_id in enumerate(profile.source_snapshot_ids):
            link_vacancy_snapshot(conn, vacancy_id=profile.vacancy_id, snapshot_id=snapshot_id, is_primary=(index == 0))
        for provenance in profile.provenance:
            insert_provenance(conn, vacancy_id=profile.vacancy_id, provenance=provenance)
        for conflict in profile.source_conflicts:
            insert_source_conflict(conn, vacancy_id=profile.vacancy_id, conflict=conflict)

    for review in pending_dedup_reviews:
        insert_vacancy_dedup_review(
            conn, incoming_snapshot_id=review["incoming_snapshot_id"],
            candidate_vacancy_id=review["candidate_vacancy_id"],
            decision_reason=review["decision_reason"], confidence=review["confidence"],
        )

    return report


def _print_report(report: PollCycleReport) -> None:
    print(f"as_of: {report.as_of.isoformat()}")
    print(f"boards considered (due): {report.boards_considered}")
    print(f"boards validated ok: {report.boards_validated_ok}")
    print(f"boards skipped (empty/error): {report.boards_skipped}")
    for v in report.board_validations:
        print(f"  - {v.company_name} [{v.source_id}] board={v.board_identifier!r}: {v.status} "
              f"({v.job_count} jobs)" + (f" -- {v.error}" if v.error else ""))
    print(f"vacancies created: {report.vacancies_created}")
    print(f"vacancies updated (merged with changes): {report.vacancies_updated}")
    print(f"vacancies re-seen unchanged: {report.vacancies_unchanged_duplicate}")
    print(f"vacancies flagged for duplicate review: {report.vacancies_review_required}")
    print(f"vacancies newly marked stale: {report.vacancies_marked_stale}")
    print(f"vacancies newly marked closed: {report.vacancies_marked_closed}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Check every board in the live registry; write nothing.")
    parser.add_argument("--run-once", action="store_true", help="Run exactly one poll cycle against the live registry.")
    args = parser.parse_args()

    if args.validate_only:
        registry = build_company_registry(load_live_boards())
        for result in validate_all_boards(registry):
            print(f"{result.company_name} [{result.source_id}] board={result.board_identifier!r}: "
                  f"{result.status} ({result.job_count} jobs)" + (f" -- {result.error}" if result.error else ""))
    elif args.run_once:
        from api.database import engine
        with engine.begin() as conn:
            _print_report(run_poll_cycle(conn))
    else:
        parser.print_help()
