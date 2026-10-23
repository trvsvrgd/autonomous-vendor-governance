from datetime import datetime, timezone
import hashlib
import io
import json
from typing import Any, Literal, Optional
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.finos.catalog import seed_finos_catalog
from app.models import (
    FinosRiskControl,
    GovernanceSignoff,
    MaterialityAssessment,
    Vendor,
)

FrameworkType = Literal[
    "sr_11_7",
    "nist_iso_42001",
    "eu_ai_act",
    "finos_calm",
    "unified_pack",
]


def build_regulatory_json_export(
    db: Session,
    *,
    framework: FrameworkType = "unified_pack",
    vendor_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Generate machine-readable Regulatory Compliance & FINOS CALM JSON artifact from live PostgreSQL state."""
    finos_controls: list[FinosRiskControl] = seed_finos_catalog(db)
    finos_map = {c.risk_id: c for c in finos_controls}

    stmt = (
        select(Vendor)
        .options(
            selectinload(Vendor.primary_owner),
            selectinload(Vendor.secondary_owner),
            selectinload(Vendor.ai_capabilities),
            selectinload(Vendor.ingestion_sources),
            selectinload(Vendor.assessments),
            selectinload(Vendor.signoffs),
        )
        .order_by(Vendor.legal_name)
    )
    if vendor_id:
        stmt = stmt.where(Vendor.vendor_id == vendor_id)

    vendors = list(db.scalars(stmt).all())
    generated_at = datetime.now(timezone.utc).isoformat()

    # 1. US Federal Reserve SR 11-7 Model Risk Management Inventory
    sr_11_7_inventory = []
    for v in vendors:
        latest_assessment: Optional[MaterialityAssessment] = (
            sorted(v.assessments, key=lambda a: a.evaluated_at, reverse=True)[0]
            if v.assessments
            else None
        )
        latest_signoff: Optional[GovernanceSignoff] = (
            sorted(v.signoffs, key=lambda s: s.created_at, reverse=True)[0]
            if v.signoffs
            else None
        )
        for cap in v.ai_capabilities:
            sr_11_7_inventory.append(
                {
                    "sr_11_7_model_id": str(cap.capability_id),
                    "vendor_id": str(v.vendor_id),
                    "vendor_legal_name": v.legal_name,
                    "primary_domain": v.primary_domain,
                    "model_tier_classification": v.risk_tier.value.upper(),
                    "product_module_name": cap.product_module_name,
                    "foundation_model_family": cap.foundation_model_family,
                    "fourth_party_model_provider": cap.model_provider,
                    "hosting_topology": cap.hosting_topology.value,
                    "autonomy_classification": cap.autonomy_classification.value,
                    "accountable_model_owner": {
                        "owner_id": str(v.primary_owner.owner_id),
                        "full_name": v.primary_owner.full_name,
                        "email": v.primary_owner.email_address,
                        "department": v.primary_owner.department,
                    },
                    "conceptual_soundness_and_ongoing_monitoring": {
                        "latest_materiality_level": latest_assessment.materiality_level.value
                        if latest_assessment
                        else "unassessed",
                        "latest_evaluation_timestamp": latest_assessment.evaluated_at.isoformat()
                        if latest_assessment
                        else None,
                        "triggered_finos_controls": latest_assessment.impacted_finos_risk_ids
                        if latest_assessment
                        else [],
                        "sr_11_7_sections_impacted": [
                            finos_map[rid].sr_11_7_mapping
                            for rid in (latest_assessment.impacted_finos_risk_ids if latest_assessment else [])
                            if rid in finos_map
                        ],
                    },
                    "effective_challenge_and_governance_signoff": {
                        "review_status": latest_signoff.review_status.value
                        if latest_signoff
                        else "awaiting_review",
                        "cryptographic_signature_hash": latest_signoff.cryptographic_signature_hash
                        if latest_signoff
                        else None,
                        "decided_at": latest_signoff.decided_at.isoformat()
                        if latest_signoff and latest_signoff.decided_at
                        else None,
                    },
                }
            )

    # 2. NIST AI RMF 1.0 (Govern, Map, Measure, Manage) & ISO/IEC 42001 Control Matrix
    nist_iso_matrix = []
    for ctrl in finos_controls:
        impacted_vendors = [
            v.legal_name
            for v in vendors
            if any(ctrl.risk_id in (a.impacted_finos_risk_ids or []) for a in v.assessments)
        ]
        nist_iso_matrix.append(
            {
                "finos_risk_id": ctrl.risk_id,
                "category_group": ctrl.category_group.value,
                "risk_name": ctrl.risk_name,
                "default_severity": ctrl.default_severity,
                "nist_ai_rmf_function_mapping": ctrl.nist_ai_rmf_mapping,
                "iso_iec_42001_annex_control": ctrl.iso_42001_mapping,
                "active_vendor_exposures": impacted_vendors,
                "exposure_count": len(impacted_vendors),
            }
        )

    # 3. EU AI Act GPAI (Article 53) & Annex III High-Risk Transparency Documentation
    eu_ai_act_disclosures = []
    for v in vendors:
        for cap in v.ai_capabilities:
            is_high_risk_or_agentic = (
                v.risk_tier.value in ("critical", "high")
                or cap.autonomy_classification.value in ("tool_calling_agent", "multi_agent_autonomous")
            )
            eu_ai_act_disclosures.append(
                {
                    "vendor_legal_name": v.legal_name,
                    "product_module": cap.product_module_name,
                    "gpai_foundation_model_family": cap.foundation_model_family,
                    "upstream_gpai_provider": cap.model_provider,
                    "annex_iii_high_risk_classification": is_high_risk_or_agentic,
                    "article_13_transparency_and_autonomy": {
                        "autonomy_mode": cap.autonomy_classification.value,
                        "mcp_or_a2a_interconnectivity": cap.mcp_or_a2a_enabled,
                    },
                    "article_10_data_governance": {
                        "trains_on_deployer_customer_data": cap.trains_on_customer_data,
                        "data_retention_days": cap.data_retention_days,
                        "zero_data_retention_compliant": cap.data_retention_days == 0
                        and not cap.trains_on_customer_data,
                    },
                    "article_14_human_oversight_owner": v.primary_owner.email_address,
                }
            )

    # 4. FINOS CALM (Common Architecture Language Model) Machine-Readable Architecture Artifact
    calm_nodes = [
        {
            "unique-id": "enterprise-ai-vendor-governance-hub",
            "node-type": "service",
            "name": "Enterprise Autonomous AI Vendor Governance Platform",
            "description": "AWS Agentic Value Accelerator v5.0 Govern Workspace & FINOS v2 Control Plane",
            "interfaces": [
                {"unique-id": "sqs-evaluation-bus", "protocol": "AMQP/SQS"},
                {"unique-id": "s3-encrypted-archive", "protocol": "HTTPS/S3-SSE-AES256"},
            ],
        }
    ]
    calm_relationships = []
    calm_controls = []

    for v in vendors:
        node_id = f"vendor-node-{v.vendor_id}"
        calm_nodes.append(
            {
                "unique-id": node_id,
                "node-type": "external-vendor-ai-system",
                "name": v.legal_name,
                "domain": v.primary_domain,
                "risk-tier": v.risk_tier.value,
                "onboarding-status": v.onboarding_status.value,
                "capabilities": [
                    {
                        "capability-id": str(c.capability_id),
                        "model-family": c.foundation_model_family,
                        "provider": c.model_provider,
                        "hosting-topology": c.hosting_topology.value,
                        "autonomy-classification": c.autonomy_classification.value,
                        "mcp-or-a2a-enabled": c.mcp_or_a2a_enabled,
                    }
                    for c in v.ai_capabilities
                ],
            }
        )
        calm_relationships.append(
            {
                "unique-id": f"rel-govern-{v.vendor_id}",
                "description": f"Continuous FINOS v2 governance monitoring of {v.legal_name}",
                "relationship-type": {
                    "connects": {
                        "source": {"node": "enterprise-ai-vendor-governance-hub"},
                        "destination": {"node": node_id},
                    }
                },
                "protocol": "HTTPS-SSRF-SafeFetch",
            }
        )

    for ctrl in finos_controls:
        calm_controls.append(
            {
                "control-id": ctrl.risk_id,
                "name": ctrl.risk_name,
                "category": ctrl.category_group.value,
                "calm-requirement": ctrl.calm_control_requirement,
            }
        )

    calm_artifact = {
        "$schema": "https://calm.finos.org/release/1.0/meta/calm.json",
        "metadata": {
            "framework": "FINOS AI Governance Framework v2 + FINOS CALM 1.0",
            "workspace_pattern": "AWS Agentic Value Accelerator v5.0 Govern",
            "generated_at": generated_at,
        },
        "nodes": calm_nodes,
        "relationships": calm_relationships,
        "controls": calm_controls,
    }

    full_bundle = {
        "export_metadata": {
            "generated_at": generated_at,
            "framework_requested": framework,
            "total_vendors_in_scope": len(vendors),
            "finos_v2_catalog_controls_count": len(finos_controls),
        },
        "sr_11_7_model_risk_inventory": sr_11_7_inventory,
        "nist_ai_rmf_and_iso_42001_matrix": nist_iso_matrix,
        "eu_ai_act_gpai_and_annex_iii": eu_ai_act_disclosures,
        "finos_calm_architecture": calm_artifact,
    }

    digest = hashlib.sha256(
        json.dumps(full_bundle, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    full_bundle["export_metadata"]["artifact_sha256_integrity_hash"] = digest

    if framework == "sr_11_7":
        return {
            "export_metadata": full_bundle["export_metadata"],
            "sr_11_7_model_risk_inventory": sr_11_7_inventory,
        }
    if framework == "nist_iso_42001":
        return {
            "export_metadata": full_bundle["export_metadata"],
            "nist_ai_rmf_and_iso_42001_matrix": nist_iso_matrix,
        }
    if framework == "eu_ai_act":
        return {
            "export_metadata": full_bundle["export_metadata"],
            "eu_ai_act_gpai_and_annex_iii": eu_ai_act_disclosures,
        }
    if framework == "finos_calm":
        return calm_artifact

    return full_bundle


def build_regulatory_examination_pdf(
    db: Session,
    *,
    framework: FrameworkType = "unified_pack",
    vendor_id: Optional[UUID] = None,
) -> bytes:
    """Generate a real downloadable PDF examination pack using ReportLab."""
    bundle = build_regulatory_json_export(db, framework="unified_pack", vendor_id=vendor_id)
    meta = bundle["export_metadata"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title="Enterprise AI Vendor Governance Examination Pack",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ExamTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "ExamH2",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ExamBody",
        parent=styles["BodyText"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1E293B"),
    )
    cell_style = ParagraphStyle(
        "ExamCell",
        parent=styles["BodyText"],
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#0F172A"),
    )

    story: list[Any] = []
    story.append(
        Paragraph(
            "Enterprise AI Vendor Governance & Regulatory Examination Pack",
            title_style,
        )
    )
    story.append(
        Paragraph(
            f"<b>Framework Scope:</b> {framework.upper()} | "
            f"<b>Generated At:</b> {meta['generated_at']} | "
            f"<b>SHA-256 Integrity:</b> <font name='Courier'>{meta['artifact_sha256_integrity_hash'][:24]}...</font>",
            body_style,
        )
    )
    story.append(Spacer(1, 10))

    # Section 1: US Federal Reserve SR 11-7 Model Risk Management Inventory
    if framework in ("sr_11_7", "unified_pack"):
        story.append(
            Paragraph(
                "1. US Federal Reserve SR 11-7 Model Risk Management Inventory",
                h2_style,
            )
        )
        sr_rows = [
            [
                Paragraph("<b>Vendor & Domain</b>", cell_style),
                Paragraph("<b>Risk Tier</b>", cell_style),
                Paragraph("<b>Foundation Model & Provider</b>", cell_style),
                Paragraph("<b>Autonomy / Hosting</b>", cell_style),
                Paragraph("<b>Accountable Owner</b>", cell_style),
                Paragraph("<b>Signoff & Hash</b>", cell_style),
            ]
        ]
        for item in bundle["sr_11_7_model_risk_inventory"]:
            sig_hash = item["effective_challenge_and_governance_signoff"].get(
                "cryptographic_signature_hash"
            ) or "Pending"
            sr_rows.append(
                [
                    Paragraph(
                        f"{item['vendor_legal_name']}<br/><font size=6.5>{item['primary_domain']}</font>",
                        cell_style,
                    ),
                    Paragraph(item["model_tier_classification"], cell_style),
                    Paragraph(
                        f"{item['foundation_model_family']}<br/>({item['fourth_party_model_provider']})",
                        cell_style,
                    ),
                    Paragraph(
                        f"{item['autonomy_classification']}<br/>{item['hosting_topology']}",
                        cell_style,
                    ),
                    Paragraph(
                        f"{item['accountable_model_owner']['full_name']}<br/>"
                        f"<font size=6.5>{item['accountable_model_owner']['department']}</font>",
                        cell_style,
                    ),
                    Paragraph(
                        f"{item['effective_challenge_and_governance_signoff']['review_status']}<br/>"
                        f"<font name='Courier' size=6>{sig_hash[:18]}</font>",
                        cell_style,
                    ),
                ]
            )
        t1 = Table(
            sr_rows,
            colWidths=[1.35 * inch, 0.7 * inch, 1.35 * inch, 1.25 * inch, 1.3 * inch, 1.45 * inch],
            repeatRows=1,
        )
        t1.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t1)
        story.append(Spacer(1, 10))

    # Section 2: NIST AI RMF & ISO/IEC 42001 Control Matrix (23 FINOS v2 Risks)
    if framework in ("nist_iso_42001", "unified_pack"):
        story.append(
            Paragraph(
                "2. FINOS AI Governance v2 / NIST AI RMF / ISO 42001 Control Matrix",
                h2_style,
            )
        )
        matrix_rows = [
            [
                Paragraph("<b>FINOS ID</b>", cell_style),
                Paragraph("<b>Risk Category & Name</b>", cell_style),
                Paragraph("<b>NIST AI RMF Mapping</b>", cell_style),
                Paragraph("<b>ISO/IEC 42001 Annex</b>", cell_style),
                Paragraph("<b>Active Exposures</b>", cell_style),
            ]
        ]
        for row in bundle["nist_ai_rmf_and_iso_42001_matrix"]:
            exposures = ", ".join(row["active_vendor_exposures"]) or "None"
            matrix_rows.append(
                [
                    Paragraph(f"<b>{row['finos_risk_id']}</b>", cell_style),
                    Paragraph(f"{row['risk_name']} ({row['category_group']})", cell_style),
                    Paragraph(row["nist_ai_rmf_function_mapping"], cell_style),
                    Paragraph(row["iso_iec_42001_annex_control"], cell_style),
                    Paragraph(exposures, cell_style),
                ]
            )
        t2 = Table(
            matrix_rows,
            colWidths=[0.95 * inch, 1.75 * inch, 1.65 * inch, 1.65 * inch, 1.4 * inch],
            repeatRows=1,
        )
        t2.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t2)
        story.append(Spacer(1, 10))

    # Section 3: EU AI Act General Purpose AI (GPAI) & Annex III High-Risk Transparency
    if framework in ("eu_ai_act", "unified_pack"):
        story.append(
            Paragraph(
                "3. EU AI Act GPAI & Annex III High-Risk Transparency Disclosures",
                h2_style,
            )
        )
        eu_rows = [
            [
                Paragraph("<b>Vendor & Module</b>", cell_style),
                Paragraph("<b>GPAI Model & Provider</b>", cell_style),
                Paragraph("<b>Annex III High-Risk</b>", cell_style),
                Paragraph("<b>Art. 10 Data / ZDR</b>", cell_style),
                Paragraph("<b>Art. 14 Oversight</b>", cell_style),
            ]
        ]
        for item in bundle["eu_ai_act_gpai_and_annex_iii"]:
            dg = item["article_10_data_governance"]
            eu_rows.append(
                [
                    Paragraph(
                        f"{item['vendor_legal_name']}<br/>{item['product_module']}",
                        cell_style,
                    ),
                    Paragraph(
                        f"{item['gpai_foundation_model_family']}<br/>({item['upstream_gpai_provider']})",
                        cell_style,
                    ),
                    Paragraph(
                        "HIGH-RISK (Annex III)"
                        if item["annex_iii_high_risk_classification"]
                        else "Standard GPAI",
                        cell_style,
                    ),
                    Paragraph(
                        f"Trains on Data: {dg['trains_on_deployer_customer_data']}<br/>"
                        f"Retention: {dg['data_retention_days']}d | ZDR: {dg['zero_data_retention_compliant']}",
                        cell_style,
                    ),
                    Paragraph(item["article_14_human_oversight_owner"], cell_style),
                ]
            )
        t3 = Table(
            eu_rows,
            colWidths=[1.5 * inch, 1.5 * inch, 1.2 * inch, 1.7 * inch, 1.5 * inch],
            repeatRows=1,
        )
        t3.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t3)

    doc.build(story)
    return buffer.getvalue()
