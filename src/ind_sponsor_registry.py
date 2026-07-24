from __future__ import annotations

import csv
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from source_schemas import CompanySponsorshipSignal, SponsorMatchMethod
from vacancy_utils import normalise_text


class SponsorRegistry:
    def __init__(self, organisations: list[tuple[str, str | None]], snapshot_date: date | None = None):
        self.organisations = organisations
        self.snapshot_date = snapshot_date

    @classmethod
    def from_csv(cls, path: str | Path, *, snapshot_date: date | None = None) -> "SponsorRegistry":
        rows = []
        with Path(path).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append((row["organisation"], row.get("kvk_number") or None))
        return cls(rows, snapshot_date=snapshot_date)

    def lookup(
        self,
        company_name: str,
        kvk_number: str | None = None,
        *,
        fuzzy_threshold: float = 0.90,
    ) -> CompanySponsorshipSignal:
        if kvk_number:
            for organisation, row_kvk in self.organisations:
                if row_kvk and row_kvk == kvk_number:
                    return CompanySponsorshipSignal(
                        recognised_sponsor=True,
                        possible_match=False,
                        human_review_required=False,
                        match_method=SponsorMatchMethod.EXACT_KVK,
                        registry_snapshot_date=self.snapshot_date,
                        matched_organisation_name=organisation,
                        match_confidence=1.0,
                    )

        target = normalise_text(company_name)
        exact_name = next(
            (organisation for organisation, _ in self.organisations if normalise_text(organisation) == target),
            None,
        )
        if exact_name:
            return CompanySponsorshipSignal(
                recognised_sponsor=True,
                possible_match=False,
                human_review_required=False,
                match_method=SponsorMatchMethod.EXACT_LEGAL_NAME,
                registry_snapshot_date=self.snapshot_date,
                matched_organisation_name=exact_name,
                match_confidence=1.0,
            )

        best_name = None
        best_score = 0.0
        for organisation, _ in self.organisations:
            score = SequenceMatcher(None, target, normalise_text(organisation)).ratio()
            if score > best_score:
                best_name, best_score = organisation, score

        if best_name and best_score >= fuzzy_threshold:
            return CompanySponsorshipSignal(
                recognised_sponsor=None,
                possible_match=True,
                human_review_required=True,
                match_method=SponsorMatchMethod.FUZZY_NAME,
                registry_snapshot_date=self.snapshot_date,
                matched_organisation_name=best_name,
                match_confidence=round(best_score, 3),
                note=(
                    "Possible match in the IND recognised-sponsor register; the legal entity is not yet verified. "
                    "Even a verified registry match would not prove that this vacancy offers sponsorship."
                ),
            )

        return CompanySponsorshipSignal(
            recognised_sponsor=False if best_score < 0.5 else None,
            possible_match=False,
            human_review_required=False,
            match_method=SponsorMatchMethod.NO_MATCH,
            registry_snapshot_date=self.snapshot_date,
            matched_organisation_name=best_name,
            match_confidence=round(best_score, 3) if best_name else None,
        )
