from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas import Category, MatchResult, ResultLane, VacancyElementValue


class VacancyIntakeSource(str, Enum):
    COMPANY_DIRECT = "company_direct"
    COMPANY_ATS_FEED = "company_ats_feed"
    PUBLIC_ATS_API = "public_ats_api"
    PUBLIC_COMPANY_PAGE = "public_company_page"
    PARTNER_FEED = "partner_feed"
    CANDIDATE_SUBMITTED = "candidate_submitted"
    MANUAL_IMPORT = "manual_import"


class AcquisitionMethod(str, Enum):
    FORM = "form"
    API = "api"
    JSON_LD = "json_ld"
    HTML = "html"
    CSV = "csv"
    WEBHOOK = "webhook"
    MANUAL_URL = "manual_url"


class VerificationStatus(str, Enum):
    AUTO_EXTRACTED = "auto_extracted"
    SOURCE_VERIFIED = "source_verified"
    HUMAN_REVIEWED = "human_reviewed"
    COMPANY_VALIDATED = "company_validated"


class TermsReviewStatus(str, Enum):
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"
    PARTNER_ONLY = "partner_only"
    PROHIBITED = "prohibited"


class RobotsPolicy(str, Enum):
    RESPECT = "respect"
    NOT_APPLICABLE_API = "not_applicable_api"
    MANUAL_ONLY = "manual_only"


class VacancyLifecycleStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    UPDATED = "updated"
    STALE = "stale"
    CLOSED = "closed"
    ARCHIVED = "archived"


class WeightingMode(str, Enum):
    COMPANY_CONFIRMED = "company_confirmed"
    TEXT_DERIVED = "text_derived"
    BALANCED_DEFAULT = "balanced_default"


class SourceTrustLevel(int, Enum):
    UNVERIFIED = 1
    PUBLIC_GENERIC = 2
    OFFICIAL_COMPANY_PAGE = 3
    OFFICIAL_ATS = 4
    COMPANY_CONFIRMED = 5


class SponsorMatchMethod(str, Enum):
    EXACT_KVK = "exact_kvk"
    EXACT_LEGAL_NAME = "exact_legal_name"
    FUZZY_NAME = "fuzzy_name"
    NO_MATCH = "no_match"


class PreliminarySignalStatus(str, Enum):
    ACTIVE = "active"
    CONVERTED = "converted"
    EXPIRED = "expired"
    DISMISSED = "dismissed"


class JobDiscoveryRunType(str, Enum):
    FULL = "full"
    PRELIMINARY_CAMPAIGN = "preliminary_campaign"
    SUBSCRIPTION_BACKFILL = "subscription_backfill"


class SourcePolicy(BaseModel):
    source_id: str
    display_name: str
    enabled: bool = False
    terms_review_status: TermsReviewStatus
    allowed_methods: List[AcquisitionMethod]
    robots_policy: RobotsPolicy = RobotsPolicy.RESPECT
    max_requests_per_minute: int = Field(default=10, ge=1, le=600)
    partner_approval_required: bool = False
    notes: str = ""

    def permits(self, method: AcquisitionMethod) -> bool:
        """Fail closed: only an enabled, explicitly approved route may be used."""
        return (
            self.enabled
            and self.terms_review_status == TermsReviewStatus.APPROVED
            and method in self.allowed_methods
            and not self.partner_approval_required
        )


class CompanyRecord(BaseModel):
    company_id: str
    legal_name: str
    display_name: str
    website_domain: str
    career_page_url: Optional[str] = None
    country: Optional[str] = None
    kvk_number: Optional[str] = None
    active: bool = True

    @field_validator("website_domain")
    @classmethod
    def normalise_domain(cls, value: str) -> str:
        value = value.lower().strip()
        for prefix in ("https://", "http://", "www."):
            if value.startswith(prefix):
                value = value[len(prefix):]
        return value.rstrip("/")


class CompanyJobSource(BaseModel):
    source_record_id: str
    company_id: str
    source_id: str
    intake_source: VacancyIntakeSource
    acquisition_method: AcquisitionMethod
    board_identifier: Optional[str] = None
    listing_url: Optional[str] = None
    enabled: bool = True
    polling_interval_minutes: int = Field(default=1440, ge=60)
    last_polled_at: Optional[datetime] = None
    next_poll_at: Optional[datetime] = None


class SourceSnapshot(BaseModel):
    snapshot_id: str
    source_record_id: str
    source_id: str
    source_url: str
    external_job_id: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    content_hash: str
    raw_payload: Dict[str, Any]
    trust_level: SourceTrustLevel


class RawVacancyRecord(BaseModel):
    source_id: str
    source_record_id: str
    intake_source: VacancyIntakeSource
    acquisition_method: AcquisitionMethod
    source_url: str
    external_job_id: Optional[str] = None
    company_name: str
    company_domain: Optional[str] = None
    title: str
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    location_text: Optional[str] = None
    department: Optional[str] = None
    employment_types: List[str] = Field(default_factory=list)
    work_mode: Optional[str] = None
    apply_url: Optional[str] = None
    date_posted: Optional[date] = None
    valid_through: Optional[date] = None
    salary: Optional[Dict[str, Any]] = None
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    trust_level: SourceTrustLevel = SourceTrustLevel.PUBLIC_GENERIC
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def require_description(self):
        if not (self.description_html or self.description_text):
            raise ValueError("A raw vacancy requires description_html or description_text")
        return self


class VacancyFieldProvenance(BaseModel):
    field_path: str
    source_snapshot_id: str
    source_url: str
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extraction_confidence: float = Field(ge=0, le=1)
    verification_status: VerificationStatus
    source_trust_level: SourceTrustLevel
    note: Optional[str] = None


class SourceConflict(BaseModel):
    field_path: str
    values_by_snapshot: Dict[str, Any]
    resolution_status: str = "unresolved"
    resolved_value: Optional[Any] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None


class CompanySponsorshipSignal(BaseModel):
    recognised_sponsor: Optional[bool] = None
    possible_match: bool = False
    human_review_required: bool = False
    match_method: SponsorMatchMethod = SponsorMatchMethod.NO_MATCH
    registry_name: str = "IND public register Work"
    registry_snapshot_date: Optional[date] = None
    matched_organisation_name: Optional[str] = None
    match_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    note: str = (
        "A recognised-sponsor registry match is a company-level signal only. "
        "It does not prove that this vacancy offers sponsorship."
    )

    @model_validator(mode="after")
    def match_method_integrity(self):
        if self.match_method == SponsorMatchMethod.FUZZY_NAME:
            self.recognised_sponsor = None
            self.possible_match = True
            self.human_review_required = True
        elif self.match_method in {SponsorMatchMethod.EXACT_KVK, SponsorMatchMethod.EXACT_LEGAL_NAME}:
            self.recognised_sponsor = True
            self.possible_match = False
        return self


class CanonicalVacancyProfile(BaseModel):
    vacancy_id: str
    company_id: Optional[str] = None
    company_name: str
    company_domain: Optional[str] = None
    title: str
    description_text: str
    external_job_ids: Dict[str, str] = Field(default_factory=dict)
    primary_source_url: str
    apply_url: Optional[str] = None
    intake_sources: List[VacancyIntakeSource]
    acquisition_methods: List[AcquisitionMethod]
    verification_status: VerificationStatus = VerificationStatus.AUTO_EXTRACTED
    lifecycle_status: VacancyLifecycleStatus = VacancyLifecycleStatus.DRAFT
    weighting_mode: WeightingMode = WeightingMode.BALANCED_DEFAULT
    weights_confirmed_by_company: bool = False
    category_weights: Dict[Category, float]
    location_text: Optional[str] = None
    department: Optional[str] = None
    employment_types: List[str] = Field(default_factory=list)
    work_mode: Optional[str] = None
    date_posted: Optional[date] = None
    valid_through: Optional[date] = None
    salary: Optional[Dict[str, Any]] = None
    element_values: List[VacancyElementValue] = Field(default_factory=list)
    provenance: List[VacancyFieldProvenance] = Field(default_factory=list)
    source_conflicts: List[SourceConflict] = Field(default_factory=list)
    sponsorship_signal: Optional[CompanySponsorshipSignal] = None
    source_snapshot_ids: List[str] = Field(default_factory=list)
    canonical_key: str
    content_hash: str
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_material_change_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    missing_poll_count: int = Field(default=0, ge=0)
    closed_reason: Optional[str] = None
    closed_at: Optional[datetime] = None
    reopened_at: Optional[datetime] = None
    reopened_reason: Optional[str] = None
    version: int = Field(default=1, ge=1)

    @field_validator("category_weights")
    @classmethod
    def weights_sum_to_100(cls, value: Dict[Category, float]):
        if abs(sum(value.values()) - 100.0) > 0.01:
            raise ValueError("Canonical vacancy category_weights must sum to 100")
        return value

    @model_validator(mode="after")
    def company_weighting_integrity(self):
        if self.weighting_mode == WeightingMode.COMPANY_CONFIRMED and not self.weights_confirmed_by_company:
            raise ValueError("company_confirmed weighting requires weights_confirmed_by_company=True")
        if self.verification_status == VerificationStatus.COMPANY_VALIDATED:
            self.weights_confirmed_by_company = True
        return self


class IngestionOutcome(BaseModel):
    profile: CanonicalVacancyProfile
    created: bool
    updated: bool
    duplicate_of: Optional[str] = None
    review_flags: List[str] = Field(default_factory=list)
    # Exposes vacancy_dedup.DuplicateDecision's own confidence and the snapshot
    # created for the incoming record, so a caller can persist a
    # vacancy_dedup_review row without re-deriving either value. Purely
    # additive: does not change what ingest() decides, only what it reports.
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    snapshot_id: Optional[str] = None


class PreliminaryOpportunitySignal(BaseModel):
    """Low-cost deterministic evidence used only for controlled campaigns.

    It is deliberately not a JobRecommendation: it has no AI explanation and
    exposes no vacancy details or score to a non-subscribed candidate.
    """

    signal_id: str
    talent_id: str
    vacancy_id: str
    result_lane: ResultLane
    overall_score_percent: Optional[float] = Field(default=None, ge=0, le=100)
    overall_coverage_percent: float = Field(ge=0, le=100)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: PreliminarySignalStatus = PreliminarySignalStatus.ACTIVE
    campaign_eligible: bool = True
    ai_explanation_generated: bool = False
    vacancy_details_visible: bool = False

    @model_validator(mode="after")
    def preliminary_signal_must_remain_lightweight(self):
        if self.ai_explanation_generated or self.vacancy_details_visible:
            raise ValueError(
                "Preliminary campaign signals may not include AI explanations or visible vacancy details"
            )
        return self


class JobDiscoveryBatchMetrics(BaseModel):
    run_type: JobDiscoveryRunType
    started_at: datetime
    candidates_considered: int = Field(default=0, ge=0)
    candidates_included: int = Field(default=0, ge=0)
    candidates_skipped: int = Field(default=0, ge=0)
    vacancies_considered: int = Field(default=0, ge=0)
    deterministic_matches_run: int = Field(default=0, ge=0)
    ai_explanations_generated: int = Field(default=0, ge=0)
    recommendations_created: int = Field(default=0, ge=0)
    preliminary_signals_created: int = Field(default=0, ge=0)


class JobRecommendation(BaseModel):
    talent_id: str
    vacancy_id: str
    match_result: MatchResult
    vacancy_verification_status: VerificationStatus
    weighting_mode: WeightingMode
    source_url: str
    provisional_public_match: bool
    freshness_status: VacancyLifecycleStatus
    explanation: str

    @model_validator(mode="after")
    def public_matches_are_provisional(self):
        if self.weighting_mode != WeightingMode.COMPANY_CONFIRMED:
            self.provisional_public_match = True
        return self
