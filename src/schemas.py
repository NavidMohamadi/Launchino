from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Category(str, Enum):
    PRACT = "PRACT"
    CAP = "CAP"
    TASK = "TASK"
    TEAM = "TEAM"
    CAREER = "CAREER"
    MOT = "MOT"
    ENV = "ENV"


class ActivationPolicy(str, Enum):
    ALWAYS = "always"
    VACANCY_ACTIVATED = "vacancy_activated"
    CANDIDATE_SELECTED = "candidate_selected"


class ValueStatus(str, Enum):
    ANSWERED = "answered"
    UNKNOWN = "unknown"
    NOT_SCORED = "not_scored"


class UnknownReason(str, Enum):
    VACANCY_NOT_SPECIFIED = "vacancy_not_specified"
    CANDIDATE_NOT_ANSWERED = "candidate_not_answered"
    CANDIDATE_DECLINED = "candidate_declined"
    ASSESSMENT_NOT_COMPLETED = "assessment_not_completed"
    CONFLICTING_INFORMATION = "conflicting_information"
    REQUIRES_VERIFICATION = "requires_verification"


class NotScoredReason(str, Enum):
    NOT_TOP_FIVE = "not_top_five"
    NOT_ACTIVATED_FOR_VACANCY = "not_activated_for_vacancy"
    OUT_OF_SCOPE_BY_DESIGN = "out_of_scope_by_design"


class JobDiscoverySubscription(str, Enum):
    NONE = "none"
    ACTIVE = "active"
    EXPIRED = "expired"


class SubscriptionSource(str, Enum):
    MANUAL = "manual"
    STRIPE = "stripe"
    TRIAL = "trial"
    UNIVERSITY = "university"
    COMPANY_SPONSORED = "company_sponsored"
    PROMOTION = "promotion"
    PREMIUM_REQUEST_APPROVED = "premium_request_approved"


class SourceType(str, Enum):
    SELF_REPORT = "self_report"
    CV = "cv"
    INTERVIEW = "interview"
    DOCUMENTED_EVIDENCE = "documented_evidence"
    OBSERVATION = "observation"
    CANDIDATE_CONFIRMATION = "candidate_confirmation"
    JOB_DESCRIPTION = "job_description"
    HIRING_MANAGER = "hiring_manager"
    TEAM_MEMBER = "team_member"
    AI_EXTRACTION = "ai_extraction"
    HUMAN_NORMALISATION = "human_normalisation"


class Alignment(str, Enum):
    ALIGNED = "aligned"
    POTENTIALLY_ALIGNED = "potentially_aligned"
    WEAK_ALIGNMENT = "weak_alignment"
    MISALIGNED = "misaligned"
    UNKNOWN = "unknown"


class EvidenceQuality(int, Enum):
    SELF_REPORT_ONLY = 1
    EXAMPLE_SUPPORTED = 2
    DOCUMENTED_OR_OBSERVED = 3
    TRIANGULATED = 4


class RequirementType(str, Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    TRAINABLE = "trainable"
    PREFERRED = "preferred"
    INFORMATION_ONLY = "information_only"


class TrainabilityWindow(str, Enum):
    NOT_TRAINABLE = "not_trainable"
    ONE_MONTH = "one_month"
    THREE_MONTHS = "three_months"
    SIX_MONTHS = "six_months"
    LONGER = "longer"
    NOT_SPECIFIED = "not_specified"


class BridgeabilityStatus(str, Enum):
    NOT_REVIEWED = "not_reviewed"
    PROMISING = "promising"
    UNCERTAIN = "uncertain"
    UNLIKELY = "unlikely"
    NOT_APPLICABLE = "not_applicable"


class ResultLane(str, Enum):
    PRIORITY_MATCH = "priority_match"
    PROMISING_MATCH = "promising_match"
    CLARIFICATION_REQUIRED = "clarification_required"
    CRITICAL_REVIEW = "critical_review"
    LOWER_ALIGNMENT = "lower_alignment"


class SharingStatus(str, Enum):
    INTERNAL_ONLY = "internal_only"
    CANDIDATE_VISIBLE = "candidate_visible"
    EMPLOYER_SHAREABLE_AFTER_APPROVAL = "employer_shareable_after_approval"


class MappingRelationship(str, Enum):
    EXACT = "exact"
    SYNONYM = "synonym"
    BROADER = "broader"
    NARROWER = "narrower"
    RELATED = "related"
    UNMAPPED = "unmapped"


class ApprovedAliasRelationship(str, Enum):
    EXACT = "exact"
    SYNONYM = "synonym"
    BROADER = "broader"
    NARROWER = "narrower"
    RELATED = "related"


class Talent(BaseModel):
    """Minimal talent account record used by access/orchestration services.

    The deterministic matching engine deliberately does not receive this model;
    it continues to operate only on Talent Fit element values and vacancy data.
    """

    talent_id: str
    full_name: str
    email: str
    profile_status: str = "registered"
    job_discovery_subscription: JobDiscoverySubscription = JobDiscoverySubscription.NONE
    subscription_expires_at: Optional[datetime] = None
    job_discovery_campaign_opt_in: bool = False
    subscription_updated_at: Optional[datetime] = None
    subscription_source: Optional[SubscriptionSource] = None

    @field_validator("subscription_expires_at", "subscription_updated_at")
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError("Subscription timestamps must be timezone-aware")
        return value


class OrdinalRange(BaseModel):
    preferred_min: int = Field(ge=1, le=5)
    preferred_max: int = Field(ge=1, le=5)
    tolerable_min: int = Field(ge=1, le=5)
    tolerable_max: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def validate_nested_ranges(self):
        if self.preferred_min > self.preferred_max:
            raise ValueError("preferred_min may not exceed preferred_max")
        if self.tolerable_min > self.tolerable_max:
            raise ValueError("tolerable_min may not exceed tolerable_max")
        if self.tolerable_min > self.preferred_min or self.preferred_max > self.tolerable_max:
            raise ValueError("The tolerable range must contain the preferred range")
        return self


def expected_activation_policy(category: Category, element_id: str) -> ActivationPolicy:
    if category in {Category.CAP, Category.TASK}:
        return ActivationPolicy.VACANCY_ACTIVATED
    if category == Category.MOT:
        return ActivationPolicy.CANDIDATE_SELECTED
    if category == Category.TEAM:
        return ActivationPolicy.ALWAYS if element_id == "TEAM-COLLAB-INTENSITY" else ActivationPolicy.VACANCY_ACTIVATED
    return ActivationPolicy.ALWAYS


class FitElement(BaseModel):
    element_id: str
    category: Category
    label: str
    definition: str
    activation_policy: ActivationPolicy
    candidate_question: str
    vacancy_question: str
    candidate_value_schema: Dict[str, Any]
    vacancy_value_schema: Dict[str, Any]
    evidence_rule: str
    comparator_key: str
    sharing_status: SharingStatus
    active: bool = True
    version: str = "2.0.0"
    is_template: bool = False

    @model_validator(mode="after")
    def validate_id_and_policy(self):
        expected_prefix = f"{self.category.value}-"
        if not self.element_id.startswith(expected_prefix):
            raise ValueError(f"element_id must begin with {expected_prefix}")
        expected_policy = expected_activation_policy(self.category, self.element_id)
        if self.activation_policy != expected_policy:
            raise ValueError(
                f"{self.element_id} must use activation_policy={expected_policy.value}, "
                f"not {self.activation_policy.value}"
            )
        return self


class FitElementAlias(BaseModel):
    alias: str
    canonical_element_id: str
    relationship: ApprovedAliasRelationship = ApprovedAliasRelationship.SYNONYM
    approved_by: str
    approved_at: date
    source_note: Optional[str] = None


class FitElementProposal(BaseModel):
    raw_term: str
    proposed_element_id: str
    proposed_category: Category
    proposed_label: str
    proposed_definition: str
    reason_new_element_is_needed: str
    proposed_by: str
    status: str = "pending_human_review"

    @field_validator("proposed_category")
    @classmethod
    def only_dynamic_categories(cls, value: Category) -> Category:
        if value not in {Category.CAP, Category.TASK}:
            raise ValueError("New dynamic elements may only be proposed for CAP or TASK")
        return value


class Evidence(BaseModel):
    evidence_id: str
    element_id: str
    source_type: SourceType
    description: str
    quality: EvidenceQuality
    observed_at: Optional[date] = None
    assessor_id: Optional[str] = None
    shareable_with_employer: bool = False


class ElementValueState(BaseModel):
    value_status: ValueStatus = ValueStatus.ANSWERED
    unknown_reason: Optional[UnknownReason] = None
    not_scored_reason: Optional[NotScoredReason] = None

    @model_validator(mode="after")
    def validate_state_reason(self):
        if self.value_status == ValueStatus.ANSWERED:
            if self.unknown_reason or self.not_scored_reason:
                raise ValueError("ANSWERED values may not carry missing/not-scored reasons")
        elif self.value_status == ValueStatus.UNKNOWN:
            if self.unknown_reason is None or self.not_scored_reason is not None:
                raise ValueError("UNKNOWN requires unknown_reason and no not_scored_reason")
        elif self.value_status == ValueStatus.NOT_SCORED:
            if self.not_scored_reason is None or self.unknown_reason is not None:
                raise ValueError("NOT_SCORED requires not_scored_reason and no unknown_reason")
        return self


class TalentElementValue(ElementValueState):
    talent_id: str
    element_id: str
    value: Dict[str, Any] = Field(default_factory=dict)
    source_type: SourceType
    evidence_ids: List[str] = Field(default_factory=list)
    last_confirmed_at: Optional[date] = None

    @model_validator(mode="after")
    def answered_requires_payload(self):
        if self.value_status == ValueStatus.ANSWERED and not self.value:
            raise ValueError("ANSWERED talent values require a non-empty value payload")
        return self


class VacancyElementValue(ElementValueState):
    vacancy_id: str
    element_id: str
    value: Dict[str, Any] = Field(default_factory=dict)
    source_type: SourceType
    item_importance: int = Field(default=3, ge=1, le=5)
    requirement_type: RequirementType = RequirementType.IMPORTANT
    trainability_window: TrainabilityWindow = TrainabilityWindow.NOT_SPECIFIED
    last_confirmed_at: Optional[date] = None

    @model_validator(mode="after")
    def answered_requires_payload(self):
        if self.value_status == ValueStatus.ANSWERED and not self.value:
            raise ValueError("ANSWERED vacancy values require a non-empty value payload")
        return self


class MatchConfiguration(BaseModel):
    vacancy_id: str
    algorithm_version: str = "2.0.0"
    category_weights: Dict[Category, float]
    minimum_overall_coverage: float = Field(default=0.70, ge=0, le=1)
    minimum_category_coverage: float = Field(default=0.50, ge=0, le=1)
    priority_score_threshold: float = Field(default=75.0, ge=0, le=100)
    promising_score_threshold: float = Field(default=60.0, ge=0, le=100)

    @field_validator("category_weights")
    @classmethod
    def weights_must_sum_to_100(cls, value):
        if not value:
            raise ValueError("category_weights may not be empty")
        total = sum(value.values())
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"category_weights must sum to 100; received {total}")
        return value


class ItemResult(BaseModel):
    talent_id: str
    vacancy_id: str
    element_id: str
    category: Category
    value_status: ValueStatus
    alignment: Optional[Alignment] = None
    score: Optional[float] = Field(default=None, ge=0, le=3)
    item_importance: int = Field(ge=1, le=5)
    requirement_type: RequirementType
    evidence_quality: Optional[EvidenceQuality] = None
    reason: str
    unknown_reason: Optional[UnknownReason] = None
    not_scored_reason: Optional[NotScoredReason] = None
    clarification_required: bool = False
    human_review_required: bool = False
    bridgeability_status: BridgeabilityStatus = BridgeabilityStatus.NOT_APPLICABLE
    bridgeability_note: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_state(self):
        if self.value_status == ValueStatus.ANSWERED:
            if self.alignment in {None, Alignment.UNKNOWN} or self.score is None:
                raise ValueError("ANSWERED item results require a known alignment and score")
            if self.unknown_reason or self.not_scored_reason:
                raise ValueError("ANSWERED item results may not have state reasons")
        elif self.value_status == ValueStatus.UNKNOWN:
            if self.alignment != Alignment.UNKNOWN or self.score is not None or self.unknown_reason is None:
                raise ValueError("UNKNOWN results require Alignment.UNKNOWN, no score, and unknown_reason")
        elif self.value_status == ValueStatus.NOT_SCORED:
            if self.alignment is not None or self.score is not None or self.not_scored_reason is None:
                raise ValueError("NOT_SCORED results require no alignment/score and a not_scored_reason")
        return self


class CategoryResult(BaseModel):
    category: Category
    score_percent: Optional[float]
    coverage_percent: float
    category_weight: float
    active_item_count: int = 0
    answered_item_count: int = 0
    not_scored_item_count: int = 0
    critical_issues: int = 0
    unknown_items: int = 0


class MatchResult(BaseModel):
    talent_id: str
    vacancy_id: str
    overall_score_percent: Optional[float]
    overall_coverage_percent: float
    category_results: List[CategoryResult]
    critical_flags: List[str]
    clarification_flags: List[str]
    lane: ResultLane
    provisional: bool
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("overall_score_percent")
    @classmethod
    def validate_score(cls, value):
        if value is not None and not 0 <= value <= 100:
            raise ValueError("overall_score_percent must be between 0 and 100")
        return value
