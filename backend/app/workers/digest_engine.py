from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aws_clients import dispatch_notification_channels
from app.config import get_settings
from app.models import (
    BusinessOwner,
    GovernanceSignoff,
    MaterialityAssessment,
    MaterialityLevel,
    ReviewStatus,
    Vendor,
)
from app.security import compute_signoff_signature_hash


def preview_non_material_digest(
    db: Session,
    *,
    window_hours: int = 24,
) -> list[dict[str, Any]]:
    """Aggregate Non-Material assessments recorded over the prior window (24h or 7d) grouped by Business Owner."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    stmt = (
        select(GovernanceSignoff, MaterialityAssessment, Vendor, BusinessOwner)
        .join(
            MaterialityAssessment,
            GovernanceSignoff.assessment_id == MaterialityAssessment.assessment_id,
        )
        .join(Vendor, GovernanceSignoff.vendor_id == Vendor.vendor_id)
        .join(
            BusinessOwner,
            GovernanceSignoff.assigned_owner_id == BusinessOwner.owner_id,
        )
        .where(
            MaterialityAssessment.materiality_level == MaterialityLevel.non_material,
            MaterialityAssessment.evaluated_at >= cutoff,
        )
        .order_by(MaterialityAssessment.evaluated_at.desc())
    )

    rows = db.execute(stmt).all()
    grouped: dict[UUID, dict[str, Any]] = {}

    for signoff, assessment, vendor, owner in rows:
        if owner.owner_id not in grouped:
            grouped[owner.owner_id] = {
                "owner_id": str(owner.owner_id),
                "owner_full_name": owner.full_name,
                "owner_email": owner.email_address,
                "department": owner.department,
                "notification_channel_preferences": owner.notification_channel_preferences,
                "window_hours": window_hours,
                "items": [],
            }
        grouped[owner.owner_id]["items"].append(
            {
                "signoff_id": str(signoff.signoff_id),
                "assessment_id": str(assessment.assessment_id),
                "vendor_id": str(vendor.vendor_id),
                "vendor_legal_name": vendor.legal_name,
                "vendor_primary_domain": vendor.primary_domain,
                "executive_summary": assessment.executive_summary,
                "evaluated_at": assessment.evaluated_at.isoformat(),
                "review_status": signoff.review_status.value,
            }
        )

    return list(grouped.values())


def dispatch_non_material_digests(
    db: Session,
    *,
    window_hours: int = 24,
) -> dict[str, Any]:
    """Dispatch aggregated Non-Material digests per Business Owner via SES/Slack/Teams and record digest_sent."""
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    now = datetime.now(timezone.utc)

    stmt = (
        select(GovernanceSignoff, MaterialityAssessment, Vendor, BusinessOwner)
        .join(
            MaterialityAssessment,
            GovernanceSignoff.assessment_id == MaterialityAssessment.assessment_id,
        )
        .join(Vendor, GovernanceSignoff.vendor_id == Vendor.vendor_id)
        .join(
            BusinessOwner,
            GovernanceSignoff.assigned_owner_id == BusinessOwner.owner_id,
        )
        .where(
            MaterialityAssessment.materiality_level == MaterialityLevel.non_material,
            MaterialityAssessment.evaluated_at >= cutoff,
            GovernanceSignoff.review_status == ReviewStatus.awaiting_review,
        )
        .order_by(MaterialityAssessment.evaluated_at.desc())
        .limit(settings.MAX_WORKER_STEPS)
    )

    rows = db.execute(stmt).all()
    by_owner: dict[UUID, list[tuple[GovernanceSignoff, MaterialityAssessment, Vendor, BusinessOwner]]] = defaultdict(list)
    for tup in rows:
        by_owner[tup[3].owner_id].append(tup)

    dispatched_summaries: list[dict[str, Any]] = []

    for owner_id, owner_rows in by_owner.items():
        owner = owner_rows[0][3]
        window_label = "24-Hour" if window_hours <= 24 else f"{window_hours // 24}-Day"
        subject = f"[AI Governance {window_label} Non-Material Digest] {len(owner_rows)} Minor Vendor Updates"

        lines = [
            f"Business Owner: {owner.full_name} ({owner.department})",
            f"Digest Window: Prior {window_hours} hours ({now.strftime('%Y-%m-%d %H:%M UTC')})",
            f"Total Non-Material Updates: {len(owner_rows)}",
            "",
            "Summary of Non-Material Vendor Updates (UI, latency, formatting, or minor bug fixes):",
            "-" * 72,
        ]

        signoff_ids: list[str] = []
        for idx, (signoff, assessment, vendor, _) in enumerate(owner_rows, start=1):
            lines.append(
                f"{idx}. {vendor.legal_name} ({vendor.primary_domain}) "
                f"[{assessment.evaluated_at.strftime('%Y-%m-%d %H:%M UTC')}]\n"
                f"   Summary: {assessment.executive_summary}"
            )
            signoff.review_status = ReviewStatus.digest_sent
            signoff.owner_decision_notes = (
                f"Automatically aggregated and dispatched in {window_label} Non-Material Digest."
            )
            signoff.decided_at = now
            signoff.cryptographic_signature_hash = compute_signoff_signature_hash(
                signoff_id=signoff.signoff_id,
                assessment_id=assessment.assessment_id,
                vendor_id=vendor.vendor_id,
                assigned_owner_id=owner.owner_id,
                idp_subject=owner.external_idp_subject,
                review_status=ReviewStatus.digest_sent,
                owner_decision_notes=signoff.owner_decision_notes,
                decided_at=now,
            )
            signoff_ids.append(str(signoff.signoff_id))

        body_text = "\n".join(lines)
        delivery = dispatch_notification_channels(
            owner_email=owner.email_address,
            owner_preferences=owner.notification_channel_preferences or {},
            subject=subject,
            body_text=body_text,
            structured_payload={
                "digest_window_hours": window_hours,
                "owner_id": str(owner.owner_id),
                "signoff_ids": signoff_ids,
            },
        )
        dispatched_summaries.append(
            {
                "owner_id": str(owner.owner_id),
                "owner_full_name": owner.full_name,
                "owner_email": owner.email_address,
                "assessments_included": len(owner_rows),
                "signoff_ids": signoff_ids,
                "delivery_channels": delivery,
            }
        )

    db.commit()
    return {
        "dispatched_at": now.isoformat(),
        "window_hours": window_hours,
        "owners_notified": len(dispatched_summaries),
        "total_assessments_digested": len(rows),
        "digests": dispatched_summaries,
    }
