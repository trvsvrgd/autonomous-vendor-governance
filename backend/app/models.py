import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OnboardingStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    under_review = "under_review"
    restricted = "restricted"


class RiskTier(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class HostingTopology(str, enum.Enum):
    vendor_hosted = "vendor_hosted"
    aws_bedrock = "aws_bedrock"
    vertex_ai = "vertex_ai"
    azure_openai = "azure_openai"
    on_premise = "on_premise"


class AutonomyClassification(str, enum.Enum):
    deterministic = "deterministic"
    assistive_copilot = "assistive_copilot"
    tool_calling_agent = "tool_calling_agent"
    multi_agent_autonomous = "multi_agent_autonomous"


class SourceType(str, enum.Enum):
    trust_center_url = "trust_center_url"
    release_notes_url = "release_notes_url"
    subprocessor_url = "subprocessor_url"
    ula_contract_pdf = "ula_contract_pdf"
    soc2_report = "soc2_report"
    inbound_email_alias = "inbound_email_alias"


class MaterialityLevel(str, enum.Enum):
    material = "material"
    non_material = "non_material"
    baseline = "baseline"


class ReviewStatus(str, enum.Enum):
    awaiting_review = "awaiting_review"
    approved = "approved"
    rejected = "rejected"
    mitigated = "mitigated"
    digest_sent = "digest_sent"


class FinosRiskCategoryGroup(str, enum.Enum):
    operational = "operational"
    security = "security"
    regulatory_compliance = "regulatory_compliance"


class BusinessOwner(Base):
    """Business Owners Table (business_owners)."""

    __tablename__ = "business_owners"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_idp_subject: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_address: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    department: Mapped[str] = mapped_column(String(128), nullable=False)
    notification_channel_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    escalation_manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_owners.owner_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    escalation_manager: Mapped[Optional["BusinessOwner"]] = relationship(
        "BusinessOwner", remote_side=[owner_id], uselist=False
    )


class Vendor(Base):
    """Vendors Table (vendors)."""

    __tablename__ = "vendors"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    primary_domain: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        SAEnum(OnboardingStatus, name="onboarding_status_enum"),
        nullable=False,
        default=OnboardingStatus.pending,
        index=True,
    )
    risk_tier: Mapped[RiskTier] = mapped_column(
        SAEnum(RiskTier, name="risk_tier_enum"),
        nullable=False,
        default=RiskTier.medium,
        index=True,
    )
    primary_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_owners.owner_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    secondary_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_owners.owner_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    primary_owner: Mapped["BusinessOwner"] = relationship(
        "BusinessOwner", foreign_keys=[primary_owner_id]
    )
    secondary_owner: Mapped[Optional["BusinessOwner"]] = relationship(
        "BusinessOwner", foreign_keys=[secondary_owner_id]
    )
    ai_capabilities: Mapped[list["VendorAICapability"]] = relationship(
        "VendorAICapability", back_populates="vendor", cascade="all, delete-orphan"
    )
    ingestion_sources: Mapped[list["IngestionSource"]] = relationship(
        "IngestionSource", back_populates="vendor", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["VendorSnapshot"]] = relationship(
        "VendorSnapshot", back_populates="vendor", cascade="all, delete-orphan"
    )
    assessments: Mapped[list["MaterialityAssessment"]] = relationship(
        "MaterialityAssessment", back_populates="vendor", cascade="all, delete-orphan"
    )
    signoffs: Mapped[list["GovernanceSignoff"]] = relationship(
        "GovernanceSignoff", back_populates="vendor", cascade="all, delete-orphan"
    )


class IngestionSource(Base):
    """Ingestion Sources Table (ingestion_sources)."""

    __tablename__ = "ingestion_sources"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type_enum"), nullable=False
    )
    target_uri_or_s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    polling_cron_schedule: Mapped[str] = mapped_column(
        String(128), nullable=False, default="0 */6 * * *"
    )
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_http_etag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_sha256_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="ingestion_sources")
    snapshots: Mapped[list["VendorSnapshot"]] = relationship(
        "VendorSnapshot", back_populates="source", cascade="all, delete-orphan"
    )


class VendorSnapshot(Base):
    """Vendor Snapshots Table (vendor_snapshots)."""

    __tablename__ = "vendor_snapshots"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_sources.source_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    s3_archive_uri: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now, nullable=False
    )

    source: Mapped["IngestionSource"] = relationship(
        "IngestionSource", back_populates="snapshots"
    )
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="snapshots")


class VendorAICapability(Base):
    """Vendor AI Capabilities Table (vendor_ai_capabilities)."""

    __tablename__ = "vendor_ai_capabilities"

    capability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_module_name: Mapped[str] = mapped_column(String(255), nullable=False)
    foundation_model_family: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    model_provider: Mapped[str] = mapped_column(String(255), nullable=False)
    hosting_topology: Mapped[HostingTopology] = mapped_column(
        SAEnum(HostingTopology, name="hosting_topology_enum"),
        nullable=False,
        default=HostingTopology.vendor_hosted,
    )
    autonomy_classification: Mapped[AutonomyClassification] = mapped_column(
        SAEnum(AutonomyClassification, name="autonomy_classification_enum"),
        nullable=False,
        default=AutonomyClassification.deterministic,
        index=True,
    )
    mcp_or_a2a_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    trains_on_customer_data: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    data_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    active_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendor_snapshots.snapshot_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="ai_capabilities")
    active_snapshot: Mapped[Optional["VendorSnapshot"]] = relationship(
        "VendorSnapshot", foreign_keys=[active_snapshot_id]
    )


class MaterialityAssessment(Base):
    """Materiality Assessments Table (materiality_assessments)."""

    __tablename__ = "materiality_assessments"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendor_snapshots.snapshot_id", ondelete="SET NULL"),
        nullable=True,
    )
    new_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendor_snapshots.snapshot_id", ondelete="CASCADE"),
        nullable=False,
    )
    materiality_level: Mapped[MaterialityLevel] = mapped_column(
        SAEnum(MaterialityLevel, name="materiality_level_enum"),
        nullable=False,
        index=True,
    )
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    detected_model_changes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    detected_agentic_changes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    impacted_finos_risk_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list
    )
    recommended_actions: Mapped[str] = mapped_column(Text, nullable=False)
    gemini_model_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now, nullable=False
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="assessments")
    previous_snapshot: Mapped[Optional["VendorSnapshot"]] = relationship(
        "VendorSnapshot", foreign_keys=[previous_snapshot_id]
    )
    new_snapshot: Mapped["VendorSnapshot"] = relationship(
        "VendorSnapshot", foreign_keys=[new_snapshot_id]
    )
    signoffs: Mapped[list["GovernanceSignoff"]] = relationship(
        "GovernanceSignoff", back_populates="assessment", cascade="all, delete-orphan"
    )


class GovernanceSignoff(Base):
    """Governance Signoffs and Audit Log Table (governance_signoffs)."""

    __tablename__ = "governance_signoffs"

    signoff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materiality_assessments.assessment_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_owners.owner_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="review_status_enum"),
        nullable=False,
        default=ReviewStatus.awaiting_review,
        index=True,
    )
    owner_decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cryptographic_signature_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    assessment: Mapped["MaterialityAssessment"] = relationship(
        "MaterialityAssessment", back_populates="signoffs"
    )
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="signoffs")
    assigned_owner: Mapped["BusinessOwner"] = relationship(
        "BusinessOwner", foreign_keys=[assigned_owner_id]
    )


class FinosRiskControl(Base):
    """FINOS AI Governance Framework v2 Reference Catalog Table (finos_risk_catalog)."""

    __tablename__ = "finos_risk_catalog"

    risk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_group: Mapped[FinosRiskCategoryGroup] = mapped_column(
        SAEnum(FinosRiskCategoryGroup, name="finos_risk_category_group_enum"),
        nullable=False,
        index=True,
    )
    risk_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    default_severity: Mapped[str] = mapped_column(String(32), nullable=False)
    sr_11_7_mapping: Mapped[str] = mapped_column(String(255), nullable=False)
    nist_ai_rmf_mapping: Mapped[str] = mapped_column(String(255), nullable=False)
    iso_42001_mapping: Mapped[str] = mapped_column(String(255), nullable=False)
    eu_ai_act_mapping: Mapped[str] = mapped_column(String(255), nullable=False)
    calm_control_requirement: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now, nullable=False
    )
