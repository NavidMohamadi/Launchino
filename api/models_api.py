from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from schemas import (
    Category, JobDiscoverySubscription, NotScoredReason, RequirementType,
    SourceType, SubscriptionSource, TrainabilityWindow, UnknownReason, ValueStatus,
)


class TalentCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=254)
    # max_length=72: bcrypt hard-fails (raises ValueError) on inputs longer than
    # 72 bytes -- an uncapped password field would let a client crash this
    # endpoint with a 500 rather than getting a clean 422.
    password: str = Field(min_length=8, max_length=72)
    job_discovery_subscription: JobDiscoverySubscription = JobDiscoverySubscription.NONE
    subscription_expires_at: Optional[datetime] = None
    job_discovery_campaign_opt_in: bool = False
    subscription_updated_at: Optional[datetime] = None
    subscription_source: Optional[SubscriptionSource] = None


class TalentOut(BaseModel):
    talent_id: UUID
    full_name: str
    email: str
    profile_status: str
    job_discovery_subscription: JobDiscoverySubscription
    subscription_expires_at: Optional[datetime] = None
    job_discovery_campaign_opt_in: bool
    subscription_updated_at: Optional[datetime] = None
    subscription_source: Optional[SubscriptionSource] = None


class CandidateLoginRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=72)


class CandidateAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    candidate: TalentOut


class CompanyCreate(BaseModel):
    legal_name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    website_domain: str = Field(min_length=1, max_length=253)
    contact_email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=72)
    career_page_url: Optional[str] = Field(default=None, max_length=2048)
    country_code: Optional[str] = Field(default=None, max_length=10)
    kvk_number: Optional[str] = Field(default=None, max_length=20)


class CompanyOut(BaseModel):
    company_id: UUID
    legal_name: str
    display_name: str
    website_domain: str
    contact_email: Optional[str] = None


class CompanyLoginRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=72)


class CompanyAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    company: CompanyOut


class AdminLoginRequest(BaseModel):
    # Plain str, not EmailStr: the admin identity is a configured constant
    # (ADMIN_EMAIL in .env) compared literally, not a real deliverable
    # mailbox -- EmailStr's reserved-TLD check (e.g. rejecting .local)
    # would otherwise constrain what admin identifiers are usable for no
    # real benefit.
    email: str = Field(max_length=254)
    password: str = Field(max_length=72)


class AdminAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SubscriptionUpdateRequest(BaseModel):
    """Admin-only, no-auth-yet manual override -- see PATCH /candidates/{id}/subscription."""

    job_discovery_subscription: JobDiscoverySubscription
    subscription_expires_at: Optional[datetime] = None
    subscription_source: Optional[SubscriptionSource] = None


class ElementValueIn(BaseModel):
    """One survey answer, shaped like a talent_element_value / vacancy_element_value row."""

    element_id: str = Field(min_length=1, max_length=100)
    value: Dict[str, Any] = Field(default_factory=dict)
    value_status: ValueStatus = ValueStatus.ANSWERED
    unknown_reason: Optional[UnknownReason] = None
    not_scored_reason: Optional[NotScoredReason] = None
    source_type: SourceType
    last_confirmed_at: Optional[date] = None


class CandidateElementValueIn(ElementValueIn):
    shareable_with_employer: bool = False


class VacancyElementValueIn(ElementValueIn):
    item_importance: int = Field(default=3, ge=1, le=5)
    requirement_type: RequirementType = RequirementType.IMPORTANT
    trainability_window: TrainabilityWindow = TrainabilityWindow.NOT_SPECIFIED


class CandidateSurveySubmission(BaseModel):
    # 200 is well above the ~41-element starter Fit Dictionary plus room for
    # vacancy-specific CAP/TASK growth -- caps against a single request
    # submitting an absurd number of fabricated entries.
    values: List[CandidateElementValueIn] = Field(max_length=200)


class VacancyWorkshopSubmission(BaseModel):
    values: List[VacancyElementValueIn] = Field(max_length=200)


class CVExtractionRequest(BaseModel):
    # 20,000 chars comfortably covers any real CV (most are under 10,000) while
    # capping the AI-extraction endpoint's per-call cost against a pasted-in
    # oversized/spam document.
    cv_text: str = Field(min_length=1, max_length=20_000)


class VacancyDescriptionExtractionRequest(BaseModel):
    description_text: str = Field(min_length=1, max_length=20_000)


class VacancyCreate(BaseModel):
    """Company-direct vacancy submission.

    Shaped like the "submission" dict src/company_intake.py's
    raw_from_company_submission() expects, plus the two fields
    canonicalise_company_submission() takes directly. Fields that
    CanonicalVacancyProfile computes itself (canonical_key, content_hash,
    first_seen_at, ...) are deliberately not accepted from the client.

    company_id is deliberately NOT a field here (unlike before auth existed):
    it's derived from the authenticated company's token in the route handler,
    never trusted from the request body -- otherwise any company could create
    a vacancy claiming to belong to a different company_id.
    """

    category_weights: Dict[Category, float]
    company_name: str = Field(min_length=1, max_length=200)
    company_domain: Optional[str] = Field(default=None, max_length=253)
    title: str = Field(min_length=1, max_length=300)
    description_text: str = Field(min_length=1, max_length=20_000)
    location_text: Optional[str] = Field(default=None, max_length=200)
    department: Optional[str] = Field(default=None, max_length=200)
    employment_types: List[str] = Field(default_factory=list, max_length=20)
    work_mode: Optional[str] = Field(default=None, max_length=50)
    apply_url: Optional[str] = Field(default=None, max_length=2048)
    date_posted: Optional[date] = None
    valid_through: Optional[date] = None
    salary: Optional[Dict[str, Any]] = None
    source_url: Optional[str] = Field(default=None, max_length=2048)
    external_job_id: Optional[str] = Field(default=None, max_length=200)


class MatchRunRequest(BaseModel):
    talent_ids: List[UUID]
    category_weights: Dict[Category, float]
    minimum_overall_coverage: float = Field(default=0.70, ge=0, le=1)
    minimum_category_coverage: float = Field(default=0.50, ge=0, le=1)
    priority_score_threshold: float = Field(default=75.0, ge=0, le=100)
    promising_score_threshold: float = Field(default=60.0, ge=0, le=100)
    algorithm_version: str = "2.0.0"
    approved_by: Optional[str] = None


class CategoryResultOut(BaseModel):
    category: Category
    score_percent: Optional[float]
    coverage_percent: float
    category_weight: float
    active_item_count: int
    answered_item_count: int
    not_scored_item_count: int
    critical_issues: int
    unknown_items: int


class MatchResultOut(BaseModel):
    talent_id: UUID
    vacancy_id: UUID
    overall_score_percent: Optional[float]
    overall_coverage_percent: float
    category_results: List[CategoryResultOut]
    critical_flags: List[str]
    clarification_flags: List[str]
    lane: str
    provisional: bool


class MatchRunOut(BaseModel):
    match_run_id: UUID
    vacancy_id: UUID
    algorithm_version: str
    results: List[MatchResultOut]


class DedupReviewResolution(BaseModel):
    decision: str = Field(description="'duplicate' or 'not_duplicate'")
    note: Optional[str] = None


class SponsorReviewResolution(BaseModel):
    decision: str = Field(description="'confirm' or 'reject'")
    note: Optional[str] = None
