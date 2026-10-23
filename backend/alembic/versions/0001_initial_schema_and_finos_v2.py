"""Initial schema for 7 core governance tables and FINOS v2 risk catalog seed.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-10-22 09:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.finos.catalog import FINOS_V2_RISK_CATALOG

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    onboarding_status_enum = postgresql.ENUM(
        "pending", "active", "under_review", "restricted",
        name="onboarding_status_enum", create_type=False
    )
    risk_tier_enum = postgresql.ENUM(
        "critical", "high", "medium", "low",
        name="risk_tier_enum", create_type=False
    )
    hosting_topology_enum = postgresql.ENUM(
        "vendor_hosted", "aws_bedrock", "vertex_ai", "azure_openai", "on_premise",
        name="hosting_topology_enum", create_type=False
    )
    autonomy_classification_enum = postgresql.ENUM(
        "deterministic", "assistive_copilot", "tool_calling_agent", "multi_agent_autonomous",
        name="autonomy_classification_enum", create_type=False
    )
    source_type_enum = postgresql.ENUM(
        "trust_center_url", "release_notes_url", "subprocessor_url",
        "ula_contract_pdf", "soc2_report", "inbound_email_alias",
        name="source_type_enum", create_type=False
    )
    materiality_level_enum = postgresql.ENUM(
        "material", "non_material", "baseline",
        name="materiality_level_enum", create_type=False
    )
    review_status_enum = postgresql.ENUM(
        "awaiting_review", "approved", "rejected", "mitigated", "digest_sent",
        name="review_status_enum", create_type=False
    )
    finos_category_enum = postgresql.ENUM(
        "operational", "security", "regulatory_compliance",
        name="finos_risk_category_group_enum", create_type=False
    )

    bind = op.get_bind()
    for enum_obj in (
        onboarding_status_enum,
        risk_tier_enum,
        hosting_topology_enum,
        autonomy_classification_enum,
        source_type_enum,
        materiality_level_enum,
        review_status_enum,
        finos_category_enum,
    ):
        enum_obj.create(bind, checkfirst=True)

    # 1. Business Owners Table (business_owners)
    op.create_table(
        "business_owners",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("external_idp_subject", sa.String(length=255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=False, unique=True),
        sa.Column("department", sa.String(length=128), nullable=False),
        sa.Column("notification_channel_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "escalation_manager_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_owners.owner_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_business_owners_external_idp_subject", "business_owners", ["external_idp_subject"])
    op.create_index("ix_business_owners_email_address", "business_owners", ["email_address"])

    # 2. Vendors Table (vendors)
    op.create_table(
        "vendors",
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("primary_domain", sa.String(length=255), nullable=False, unique=True),
        sa.Column("onboarding_status", onboarding_status_enum, nullable=False),
        sa.Column("risk_tier", risk_tier_enum, nullable=False),
        sa.Column(
            "primary_owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_owners.owner_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "secondary_owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_owners.owner_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_vendors_legal_name", "vendors", ["legal_name"])
    op.create_index("ix_vendors_primary_domain", "vendors", ["primary_domain"])
    op.create_index("ix_vendors_onboarding_status", "vendors", ["onboarding_status"])
    op.create_index("ix_vendors_risk_tier", "vendors", ["risk_tier"])
    op.create_index("ix_vendors_primary_owner_id", "vendors", ["primary_owner_id"])

    # 3. Ingestion Sources Table (ingestion_sources)
    op.create_table(
        "ingestion_sources",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("target_uri_or_s3_key", sa.Text(), nullable=False),
        sa.Column("polling_cron_schedule", sa.String(length=128), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_http_etag", sa.String(length=255), nullable=True),
        sa.Column("last_sha256_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ingestion_sources_vendor_id", "ingestion_sources", ["vendor_id"])

    # 4. Vendor Snapshots Table (vendor_snapshots)
    op.create_table(
        "vendor_snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_sources.source_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_extracted_text", sa.Text(), nullable=False),
        sa.Column("content_sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("s3_archive_uri", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_vendor_snapshots_source_id", "vendor_snapshots", ["source_id"])
    op.create_index("ix_vendor_snapshots_vendor_id", "vendor_snapshots", ["vendor_id"])
    op.create_index("ix_vendor_snapshots_content_sha256_hash", "vendor_snapshots", ["content_sha256_hash"])

    # 5. Vendor AI Capabilities Table (vendor_ai_capabilities)
    op.create_table(
        "vendor_ai_capabilities",
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_module_name", sa.String(length=255), nullable=False),
        sa.Column("foundation_model_family", sa.String(length=255), nullable=False),
        sa.Column("model_provider", sa.String(length=255), nullable=False),
        sa.Column("hosting_topology", hosting_topology_enum, nullable=False),
        sa.Column("autonomy_classification", autonomy_classification_enum, nullable=False),
        sa.Column("mcp_or_a2a_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("trains_on_customer_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("data_retention_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "active_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_snapshots.snapshot_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_vendor_ai_capabilities_vendor_id", "vendor_ai_capabilities", ["vendor_id"])
    op.create_index(
        "ix_vendor_ai_capabilities_foundation_model_family",
        "vendor_ai_capabilities",
        ["foundation_model_family"],
    )
    op.create_index(
        "ix_vendor_ai_capabilities_autonomy_classification",
        "vendor_ai_capabilities",
        ["autonomy_classification"],
    )

    # 6. Materiality Assessments Table (materiality_assessments)
    op.create_table(
        "materiality_assessments",
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "previous_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_snapshots.snapshot_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "new_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_snapshots.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("materiality_level", materiality_level_enum, nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("detected_model_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("detected_agentic_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("impacted_finos_risk_ids", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("recommended_actions", sa.Text(), nullable=False),
        sa.Column("gemini_model_identifier", sa.String(length=128), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_materiality_assessments_vendor_id", "materiality_assessments", ["vendor_id"])
    op.create_index("ix_materiality_assessments_materiality_level", "materiality_assessments", ["materiality_level"])

    # 7. Governance Signoffs and Audit Log Table (governance_signoffs)
    op.create_table(
        "governance_signoffs",
        sa.Column("signoff_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("materiality_assessments.assessment_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_owners.owner_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("review_status", review_status_enum, nullable=False),
        sa.Column("owner_decision_notes", sa.Text(), nullable=True),
        sa.Column("cryptographic_signature_hash", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_governance_signoffs_assessment_id", "governance_signoffs", ["assessment_id"])
    op.create_index("ix_governance_signoffs_vendor_id", "governance_signoffs", ["vendor_id"])
    op.create_index("ix_governance_signoffs_assigned_owner_id", "governance_signoffs", ["assigned_owner_id"])
    op.create_index("ix_governance_signoffs_review_status", "governance_signoffs", ["review_status"])

    # 8. FINOS AI Governance Framework v2 Reference Catalog Table (finos_risk_catalog)
    finos_table = op.create_table(
        "finos_risk_catalog",
        sa.Column("risk_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("category_group", finos_category_enum, nullable=False),
        sa.Column("risk_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("default_severity", sa.String(length=32), nullable=False),
        sa.Column("sr_11_7_mapping", sa.String(length=255), nullable=False),
        sa.Column("nist_ai_rmf_mapping", sa.String(length=255), nullable=False),
        sa.Column("iso_42001_mapping", sa.String(length=255), nullable=False),
        sa.Column("eu_ai_act_mapping", sa.String(length=255), nullable=False),
        sa.Column("calm_control_requirement", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_finos_risk_catalog_category_group", "finos_risk_catalog", ["category_group"])

    # Seed the 23 Official FINOS AI Governance Framework v2 Risk Categories
    op.bulk_insert(finos_table, FINOS_V2_RISK_CATALOG)


def downgrade() -> None:
    op.drop_table("finos_risk_catalog")
    op.drop_table("governance_signoffs")
    op.drop_table("materiality_assessments")
    op.drop_table("vendor_ai_capabilities")
    op.drop_table("vendor_snapshots")
    op.drop_table("ingestion_sources")
    op.drop_table("vendors")
    op.drop_table("business_owners")

    bind = op.get_bind()
    for enum_name in (
        "finos_risk_category_group_enum",
        "review_status_enum",
        "materiality_level_enum",
        "source_type_enum",
        "autonomy_classification_enum",
        "hosting_topology_enum",
        "risk_tier_enum",
        "onboarding_status_enum",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
