from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aws_clients import (
    dispatch_notification_channels,
    get_sqs_client,
    publish_sqs_message,
)
from app.config import get_settings
from app.finos.catalog import seed_finos_catalog
from app.inference.gemini_evaluator import GeminiGovernanceEvaluator
from app.models import (
    AutonomyClassification,
    FinosRiskControl,
    GovernanceSignoff,
    MaterialityAssessment,
    MaterialityLevel,
    OnboardingStatus,
    ReviewStatus,
    Vendor,
    VendorAICapability,
    VendorSnapshot,
)

logger = logging.getLogger(__name__)


def run_materiality_evaluation_for_snapshot(
    db: Session,
    *,
    vendor_id: UUID,
    new_snapshot_id: UUID,
    previous_snapshot_id: Optional[UUID] = None,
) -> MaterialityAssessment:
    """Execute GeminiGovernanceEvaluator on a captured VendorSnapshot and record assessment + signoff."""
    vendor = db.scalar(select(Vendor).where(Vendor.vendor_id == vendor_id))
    if not vendor:
        raise ValueError(f"Vendor {vendor_id} not found.")

    new_snapshot = db.scalar(
        select(VendorSnapshot).where(VendorSnapshot.snapshot_id == new_snapshot_id)
    )
    if not new_snapshot:
        raise ValueError(f"New snapshot {new_snapshot_id} not found.")

    prev_snapshot: Optional[VendorSnapshot] = None
    if previous_snapshot_id:
        prev_snapshot = db.scalar(
            select(VendorSnapshot).where(VendorSnapshot.snapshot_id == previous_snapshot_id)
        )
    else:
        prev_snapshot = db.scalar(
            select(VendorSnapshot)
            .where(
                VendorSnapshot.source_id == new_snapshot.source_id,
                VendorSnapshot.snapshot_id != new_snapshot.snapshot_id,
                VendorSnapshot.captured_at <= new_snapshot.captured_at,
            )
            .order_by(VendorSnapshot.captured_at.desc())
            .limit(1)
        )

    finos_rows: list[FinosRiskControl] = seed_finos_catalog(db)
    finos_catalog_dicts = [
        {
            "risk_id": r.risk_id,
            "category_group": r.category_group.value,
            "risk_name": r.risk_name,
            "description": r.description,
            "default_severity": r.default_severity,
            "sr_11_7_mapping": r.sr_11_7_mapping,
            "nist_ai_rmf_mapping": r.nist_ai_rmf_mapping,
            "iso_42001_mapping": r.iso_42001_mapping,
            "eu_ai_act_mapping": r.eu_ai_act_mapping,
            "calm_control_requirement": r.calm_control_requirement,
        }
        for r in finos_rows
    ]

    capabilities = list(
        db.scalars(
            select(VendorAICapability).where(VendorAICapability.vendor_id == vendor.vendor_id)
        ).all()
    )
    capabilities_state = [
        {
            "capability_id": str(c.capability_id),
            "product_module_name": c.product_module_name,
            "foundation_model_family": c.foundation_model_family,
            "model_provider": c.model_provider,
            "hosting_topology": c.hosting_topology.value,
            "autonomy_classification": c.autonomy_classification.value,
            "mcp_or_a2a_enabled": c.mcp_or_a2a_enabled,
            "trains_on_customer_data": c.trains_on_customer_data,
            "data_retention_days": c.data_retention_days,
        }
        for c in capabilities
    ]

    baseline_state = {
        "vendor_id": str(vendor.vendor_id),
        "vendor_legal_name": vendor.legal_name,
        "primary_domain": vendor.primary_domain,
        "risk_tier": vendor.risk_tier.value,
        "is_initial_baseline": prev_snapshot is None,
        "previous_snapshot_id": str(prev_snapshot.snapshot_id) if prev_snapshot else None,
        "previous_snapshot_text": prev_snapshot.raw_extracted_text if prev_snapshot else "",
        "current_capabilities": capabilities_state,
    }

    evaluator = GeminiGovernanceEvaluator()
    eval_result = evaluator.evaluateVendorDiff(
        baselineState=baseline_state,
        newSnapshotText=new_snapshot.raw_extracted_text,
        finosCatalog=finos_catalog_dicts,
    )

    now = datetime.now(timezone.utc)
    assessment = MaterialityAssessment(
        vendor_id=vendor.vendor_id,
        previous_snapshot_id=prev_snapshot.snapshot_id if prev_snapshot else None,
        new_snapshot_id=new_snapshot.snapshot_id,
        materiality_level=eval_result.materiality_level,
        executive_summary=eval_result.executive_summary,
        detected_model_changes=eval_result.detected_model_changes.model_dump(),
        detected_agentic_changes=eval_result.detected_agentic_changes.model_dump(),
        impacted_finos_risk_ids=eval_result.impacted_finos_risk_ids,
        recommended_actions=eval_result.recommended_actions,
        gemini_model_identifier=eval_result.gemini_model_identifier,
        evaluated_at=now,
    )
    db.add(assessment)
    db.flush()

    # Synchronize vendor AI capability inventory with detected model / agentic shifts
    if capabilities:
        primary_cap = capabilities[0]
        primary_cap.active_snapshot_id = new_snapshot.snapshot_id
        mc = eval_result.detected_model_changes
        ac = eval_result.detected_agentic_changes
        if mc.new_model_family:
            primary_cap.foundation_model_family = mc.new_model_family
        if mc.new_model_provider:
            primary_cap.model_provider = mc.new_model_provider
        if mc.trains_on_customer_data is not None:
            primary_cap.trains_on_customer_data = mc.trains_on_customer_data
        if mc.new_data_retention_days is not None:
            primary_cap.data_retention_days = mc.new_data_retention_days
        if ac.mcp_server_introduced or ac.a2a_communication_introduced:
            primary_cap.mcp_or_a2a_enabled = True
        if ac.new_autonomy_classification in AutonomyClassification._value2member_map_:
            primary_cap.autonomy_classification = AutonomyClassification(
                ac.new_autonomy_classification
            )

    # Create GovernanceSignoff record for accountable business owner
    signoff = GovernanceSignoff(
        assessment_id=assessment.assessment_id,
        vendor_id=vendor.vendor_id,
        assigned_owner_id=vendor.primary_owner_id,
        review_status=ReviewStatus.awaiting_review,
    )
    db.add(signoff)

    if eval_result.materiality_level == MaterialityLevel.material:
        vendor.onboarding_status = OnboardingStatus.under_review
    elif vendor.onboarding_status == OnboardingStatus.pending:
        vendor.onboarding_status = OnboardingStatus.active

    db.commit()
    db.refresh(assessment)

    # Immediately notify accountable Business Owner via Slack / Teams / Jira / SES on Material shift
    if eval_result.materiality_level == MaterialityLevel.material and vendor.primary_owner:
        owner = vendor.primary_owner
        subject = (
            f"[MATERIAL AI GOVERNANCE ALERT] {vendor.legal_name} ({vendor.primary_domain}) "
            f"- {len(eval_result.impacted_finos_risk_ids)} FINOS v2 Risks Triggered"
        )
        body = (
            f"Accountable Owner: {owner.full_name} ({owner.department})\n"
            f"Vendor: {vendor.legal_name} (Risk Tier: {vendor.risk_tier.value.upper()})\n"
            f"Materiality Level: MATERIAL\n"
            f"Impacted FINOS v2 Controls: {', '.join(eval_result.impacted_finos_risk_ids)}\n\n"
            f"Executive Summary:\n{eval_result.executive_summary}\n\n"
            f"Recommended Actions:\n{eval_result.recommended_actions}\n"
        )
        dispatch_notification_channels(
            owner_email=owner.email_address,
            owner_preferences=owner.notification_channel_preferences or {},
            subject=subject,
            body_text=body,
            structured_payload={
                "assessment_id": str(assessment.assessment_id),
                "signoff_id": str(signoff.signoff_id),
                "vendor_id": str(vendor.vendor_id),
                "impacted_finos_risk_ids": eval_result.impacted_finos_risk_ids,
            },
        )

    return assessment


def drain_evaluation_sqs_queue(db: Session, *, max_steps: Optional[int] = None) -> dict[str, Any]:
    """Consume pending messages from SQS_EVALUATION_QUEUE_URL with a strict max_step limit."""
    settings = get_settings()
    step_limit = min(max_steps or settings.MAX_WORKER_STEPS, settings.MAX_WORKER_STEPS)
    processed = 0
    failed = 0

    try:
        sqs = get_sqs_client()
    except Exception as exc:
        return {"processed": 0, "failed": 0, "error": str(exc)}

    for _ in range(step_limit):
        try:
            resp = sqs.receive_message(
                QueueUrl=settings.SQS_EVALUATION_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=1,
            )
        except Exception as exc:
            logger.debug("SQS evaluation queue receive stopped: %s", exc)
            break

        messages = resp.get("Messages") or []
        if not messages:
            break

        msg = messages[0]
        receipt_handle = msg["ReceiptHandle"]
        try:
            body = json.loads(msg["Body"])
            run_materiality_evaluation_for_snapshot(
                db,
                vendor_id=UUID(body["vendor_id"]),
                new_snapshot_id=UUID(body["new_snapshot_id"]),
                previous_snapshot_id=UUID(body["previous_snapshot_id"])
                if body.get("previous_snapshot_id")
                else None,
            )
            sqs.delete_message(
                QueueUrl=settings.SQS_EVALUATION_QUEUE_URL,
                ReceiptHandle=receipt_handle,
            )
            processed += 1
        except Exception as exc:
            failed += 1
            logger.error("Evaluation job failed, routing to DLQ: %s", exc)
            publish_sqs_message(
                settings.SQS_EVALUATION_DLQ_URL,
                {"failed_message": msg.get("Body"), "error": str(exc)},
            )
            sqs.delete_message(
                QueueUrl=settings.SQS_EVALUATION_QUEUE_URL,
                ReceiptHandle=receipt_handle,
            )

    return {"processed": processed, "failed": failed, "max_step_limit": step_limit}
