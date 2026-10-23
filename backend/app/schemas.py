from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import (
    AutonomyClassification,
    FinosRiskCategoryGroup,
    HostingTopology,
    MaterialityLevel,
    OnboardingStatus,
    ReviewStatus,
    RiskTier,
    SourceType,
)


# ---------------------------------------------------------------------------
# Business Owner Schemas
# ---------------------------------------------------------------------------
class BusinessOwnerCreate(BaseModel):
    external_idp_subject: str = Field(..., min_length=2, max_length=255)
    full_name: str = Field(..., min_length=2, max_length=255)
    email_address: EmailStr
    department: str = Field(..., min_length=2, max_length=128)
    notification_channel_preferences: dict[str, Any] = Field(
        default_factory=lambda: {
            "email_enabled": True,
            "slack_webhook_url": None,
            "teams_webhook_url": None,
            "jira_webhook_url": None,
            "digest_frequency": "24h",
        }
    )
    escalation_manager_id: Optional[UUID] = None


class BusinessOwnerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    owner_id: UUID
    external_idp_subject: str
    full_name: str
    email_address: str
    department: str
    notification_channel_preferences: dict[str, Any]
    escalation_manager_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AI Capability & Ingestion Source Schemas
# ---------------------------------------------------------------------------
class VendorAICapabilityCreate(BaseModel):
    product_module_name: str = Field(..., min_length=1, max_length=255)
    foundation_model_family: str = Field(..., min_length=1, max_length=255)
    model_provider: str = Field(..., min_length=1, max_length=255)
    hosting_topology: HostingTopology = HostingTopology.vendor_hosted
    autonomy_classification: AutonomyClassification = AutonomyClassification.deterministic
    mcp_or_a2a_enabled: bool = False
    trains_on_customer_data: bool = False
    data_retention_days: int = Field(default=0, ge=0)


class VendorAICapabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    capability_id: UUID
    vendor_id: UUID
    product_module_name: str
    foundation_model_family: str
    model_provider: str
    hosting_topology: HostingTopology
    autonomy_classification: AutonomyClassification
    mcp_or_a2a_enabled: bool
    trains_on_customer_data: bool
    data_retention_days: int
    active_snapshot_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class IngestionSourceCreate(BaseModel):
    source_type: SourceType
    target_uri_or_s3_key: str = Field(..., min_length=3)
    polling_cron_schedule: str = Field(default="0 */6 * * *")


class IngestionSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: UUID
    vendor_id: UUID
    source_type: SourceType
    target_uri_or_s3_key: str
    polling_cron_schedule: str
    last_polled_at: Optional[datetime]
    last_http_etag: Optional[str]
    last_sha256_hash: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Vendor Onboarding & Command Center Schemas
# ---------------------------------------------------------------------------
class VendorOnboardRequest(BaseModel):
    legal_name: str = Field(..., min_length=2, max_length=255)
    primary_domain: str = Field(..., min_length=3, max_length=255)
    onboarding_status: OnboardingStatus = OnboardingStatus.active
    risk_tier: RiskTier = RiskTier.high
    primary_owner_id: UUID
    secondary_owner_id: Optional[UUID] = None
    ai_capabilities: list[VendorAICapabilityCreate] = Field(default_factory=list)
    ingestion_sources: list[IngestionSourceCreate] = Field(default_factory=list)
    trigger_immediate_baseline: bool = True


class VendorSummaryRow(BaseModel):
    vendor_id: UUID
    legal_name: str
    primary_domain: str
    onboarding_status: OnboardingStatus
    risk_tier: RiskTier
    primary_owner: BusinessOwnerResponse
    secondary_owner: Optional[BusinessOwnerResponse] = None
    ai_capabilities: list[VendorAICapabilityResponse]
    active_material_alerts_count: int
    latest_review_status: Optional[ReviewStatus] = None
    latest_assessment_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CommandCenterKPIs(BaseModel):
    total_vendors_monitored: int
    active_material_alerts_awaiting_signoff: int
    autonomous_agent_vendor_percentage: float
    critical_or_high_risk_vendors: int
    total_snapshots_archived: int


class CommandCenterResponse(BaseModel):
    kpis: CommandCenterKPIs
    vendors: list[VendorSummaryRow]
    total_count: int


# ---------------------------------------------------------------------------
# Snapshot, Assessment & Gemini Harness Bridge Schemas
# ---------------------------------------------------------------------------
class VendorSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_id: UUID
    source_id: UUID
    vendor_id: UUID
    raw_extracted_text: str
    content_sha256_hash: str
    s3_archive_uri: str
    captured_at: datetime


class DetectedModelChangesSchema(BaseModel):
    previous_model_family: Optional[str] = None
    new_model_family: Optional[str] = None
    previous_model_provider: Optional[str] = None
    new_model_provider: Optional[str] = None
    previous_hosting_topology: Optional[str] = None
    new_hosting_topology: Optional[str] = None
    fourth_party_providers_added: list[str] = Field(default_factory=list)
    hosting_geography_changed: bool = False
    model_family_swapped: bool = False
    trains_on_customer_data_changed: bool = False
    trains_on_customer_data: Optional[bool] = None
    data_retention_changed: bool = False
    new_data_retention_days: Optional[int] = None
    zero_data_retention_removed: bool = False


class DetectedAgenticChangesSchema(BaseModel):
    previous_autonomy_classification: Optional[str] = None
    new_autonomy_classification: Optional[str] = None
    autonomous_execution_introduced: bool = False
    external_tool_invocation_introduced: bool = False
    mcp_server_introduced: bool = False
    a2a_communication_introduced: bool = False
    sandbox_or_code_execution_changed: bool = False
    summary_of_agentic_shifts: str = ""


class GeminiEvaluationResultSchema(BaseModel):
    """Strict schema validated by GeminiGovernanceEvaluator."""

    materiality_level: MaterialityLevel
    executive_summary: str = Field(..., min_length=10)
    detected_model_changes: DetectedModelChangesSchema
    detected_agentic_changes: DetectedAgenticChangesSchema
    impacted_finos_risk_ids: list[str] = Field(default_factory=list)
    finos_severity_increased: bool = False
    recommended_actions: str = Field(..., min_length=10)
    gemini_model_identifier: str


class MaterialityAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_id: UUID
    vendor_id: UUID
    previous_snapshot_id: Optional[UUID]
    new_snapshot_id: UUID
    materiality_level: MaterialityLevel
    executive_summary: str
    detected_model_changes: dict[str, Any]
    detected_agentic_changes: dict[str, Any]
    impacted_finos_risk_ids: list[str]
    recommended_actions: str
    gemini_model_identifier: str
    evaluated_at: datetime


# ---------------------------------------------------------------------------
# Triage & Governance Signoff Schemas
# ---------------------------------------------------------------------------
class SignoffDecisionAction(BaseModel):
    action: Literal["approve", "require_remediation", "escalate_to_legal"]
    owner_decision_notes: str = Field(..., min_length=5, max_length=4000)
    actor_owner_id: Optional[UUID] = None


class GovernanceSignoffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signoff_id: UUID
    assessment_id: UUID
    vendor_id: UUID
    assigned_owner_id: UUID
    review_status: ReviewStatus
    owner_decision_notes: Optional[str]
    cryptographic_signature_hash: Optional[str]
    decided_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class FinosRiskControlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risk_id: str
    category_group: FinosRiskCategoryGroup
    risk_name: str
    description: str
    default_severity: str
    sr_11_7_mapping: str
    nist_ai_rmf_mapping: str
    iso_42001_mapping: str
    eu_ai_act_mapping: str
    calm_control_requirement: dict[str, Any]


class TriageQueueItem(BaseModel):
    signoff: GovernanceSignoffResponse
    assessment: MaterialityAssessmentResponse
    vendor_id: UUID
    vendor_legal_name: str
    vendor_primary_domain: str
    vendor_risk_tier: RiskTier
    assigned_owner: BusinessOwnerResponse
    previous_snapshot_text: str
    new_snapshot_text: str
    previous_snapshot_captured_at: Optional[datetime]
    new_snapshot_captured_at: datetime
    source_type: SourceType
    source_uri: str
    triggered_finos_controls: list[FinosRiskControlResponse]


class VendorDetailResponse(BaseModel):
    vendor: VendorSummaryRow
    ingestion_sources: list[IngestionSourceResponse]
    snapshots: list[VendorSnapshotResponse]
    assessments: list[MaterialityAssessmentResponse]
    signoffs: list[GovernanceSignoffResponse]
