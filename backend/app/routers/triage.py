from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.aws_clients import dispatch_notification_channels
from app.database import get_db
from app.finos.catalog import seed_finos_catalog
from app.models import (
    BusinessOwner,
    FinosRiskControl,
    GovernanceSignoff,
    IngestionSource,
    MaterialityAssessment,
    MaterialityLevel,
    OnboardingStatus,
    ReviewStatus,
    SourceType,
    Vendor,
    VendorSnapshot,
)
from app.schemas import (
    BusinessOwnerResponse,
    FinosRiskControlResponse,
    GovernanceSignoffResponse,
    MaterialityAssessmentResponse,
    SignoffDecisionAction,
    TriageQueueItem,
)
from app.security import (
    CorporateIdentityContext,
    compute_signoff_signature_hash,
    resolve_corporate_identity,
)

router = APIRouter(prefix="/triage", tags=["Material Change Triage & Signoff Queue"])


@router.get("", response_model=list[TriageQueueItem])
def list_triage_and_signoff_queue(
    materiality_level: Optional[MaterialityLevel] = Query(default=None),
    review_status: Optional[ReviewStatus] = Query(default=None),
    vendor_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[TriageQueueItem]:
    """Return Material Change Triage and Signoff Queue items with side-by-side snapshots & FINOS controls."""
    finos_rows: list[FinosRiskControl] = seed_finos_catalog(db)
    finos_map = {
        r.risk_id: FinosRiskControlResponse.model_validate(r) for r in finos_rows
    }

    stmt = (
        select(GovernanceSignoff)
        .options(
            selectinload(GovernanceSignoff.assessment).selectinload(
                MaterialityAssessment.previous_snapshot
            ),
            selectinload(GovernanceSignoff.assessment).selectinload(
                MaterialityAssessment.new_snapshot
            ),
            selectinload(GovernanceSignoff.vendor),
            selectinload(GovernanceSignoff.assigned_owner),
        )
        .order_by(GovernanceSignoff.created_at.desc())
    )

    if review_status:
        stmt = stmt.where(GovernanceSignoff.review_status == review_status)
    if vendor_id:
        stmt = stmt.where(GovernanceSignoff.vendor_id == vendor_id)

    signoffs = list(db.scalars(stmt).all())
    items: list[TriageQueueItem] = []

    for sg in signoffs:
        assessment = sg.assessment
        if not assessment:
            continue
        if materiality_level and assessment.materiality_level != materiality_level:
            continue

        new_snap: Optional[VendorSnapshot] = assessment.new_snapshot
        prev_snap: Optional[VendorSnapshot] = assessment.previous_snapshot

        source = (
            db.scalar(
                select(IngestionSource).where(
                    IngestionSource.source_id == new_snap.source_id
                )
            )
            if new_snap
            else None
        )

        triggered_controls = [
            finos_map[rid]
            for rid in (assessment.impacted_finos_risk_ids or [])
            if rid in finos_map
        ]

        items.append(
            TriageQueueItem(
                signoff=GovernanceSignoffResponse.model_validate(sg),
                assessment=MaterialityAssessmentResponse.model_validate(assessment),
                vendor_id=sg.vendor.vendor_id,
                vendor_legal_name=sg.vendor.legal_name,
                vendor_primary_domain=sg.vendor.primary_domain,
                vendor_risk_tier=sg.vendor.risk_tier,
                assigned_owner=BusinessOwnerResponse.model_validate(sg.assigned_owner),
                previous_snapshot_text=(
                    prev_snap.raw_extracted_text
                    if prev_snap
                    else "(Initial Baseline Capture — No Prior Snapshot Recorded)"
                ),
                new_snapshot_text=new_snap.raw_extracted_text if new_snap else "",
                previous_snapshot_captured_at=prev_snap.captured_at if prev_snap else None,
                new_snapshot_captured_at=(
                    new_snap.captured_at if new_snap else assessment.evaluated_at
                ),
                source_type=(
                    source.source_type if source else SourceType.trust_center_url
                ),
                source_uri=(
                    source.target_uri_or_s3_key
                    if source
                    else f"https://{sg.vendor.primary_domain}"
                ),
                triggered_finos_controls=triggered_controls,
            )
        )

    return items


@router.post("/{signoff_id}/decision", response_model=GovernanceSignoffResponse)
def submit_governance_signoff_decision(
    signoff_id: UUID,
    payload: SignoffDecisionAction,
    identity: CorporateIdentityContext = Depends(resolve_corporate_identity),
    db: Session = Depends(get_db),
) -> GovernanceSignoff:
    """Record an immutable cryptographic signoff decision (Approve, Require Vendor Remediation, Escalate to Legal)."""
    signoff = db.scalar(
        select(GovernanceSignoff)
        .options(
            selectinload(GovernanceSignoff.vendor),
            selectinload(GovernanceSignoff.assessment),
            selectinload(GovernanceSignoff.assigned_owner),
        )
        .where(GovernanceSignoff.signoff_id == signoff_id)
    )
    if not signoff:
        raise HTTPException(status_code=404, detail="Governance signoff record not found.")

    actor_owner: Optional[BusinessOwner] = None
    if payload.actor_owner_id:
        actor_owner = db.scalar(
            select(BusinessOwner).where(BusinessOwner.owner_id == payload.actor_owner_id)
        )
    if actor_owner is None:
        actor_owner = identity.owner or signoff.assigned_owner

    now = datetime.now(timezone.utc)
    vendor = signoff.vendor

    if payload.action == "approve":
        target_status = ReviewStatus.approved
        vendor.onboarding_status = OnboardingStatus.active
        decision_prefix = "[APPROVED]"
    elif payload.action == "require_remediation":
        target_status = ReviewStatus.mitigated
        vendor.onboarding_status = OnboardingStatus.under_review
        decision_prefix = "[VENDOR REMEDIATION REQUIRED]"
    elif payload.action == "escalate_to_legal":
        target_status = ReviewStatus.rejected
        vendor.onboarding_status = OnboardingStatus.restricted
        decision_prefix = "[ESCALATED TO LEGAL & RESTRICTED]"
        if signoff.assigned_owner and signoff.assigned_owner.escalation_manager_id:
            signoff.assigned_owner_id = signoff.assigned_owner.escalation_manager_id
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {payload.action}")

    formatted_notes = (
        f"{decision_prefix} Signed by {actor_owner.full_name} ({actor_owner.email_address}): "
        f"{payload.owner_decision_notes.strip()}"
    )

    sig_hash = compute_signoff_signature_hash(
        signoff_id=signoff.signoff_id,
        assessment_id=signoff.assessment_id,
        vendor_id=signoff.vendor_id,
        assigned_owner_id=signoff.assigned_owner_id,
        idp_subject=actor_owner.external_idp_subject,
        review_status=target_status,
        owner_decision_notes=formatted_notes,
        decided_at=now,
    )

    # Update the awaiting_review row or append a new immutable audit row if already decided
    if signoff.review_status == ReviewStatus.awaiting_review:
        signoff.review_status = target_status
        signoff.owner_decision_notes = formatted_notes
        signoff.cryptographic_signature_hash = sig_hash
        signoff.decided_at = now
        target_record = signoff
    else:
        new_signoff = GovernanceSignoff(
            assessment_id=signoff.assessment_id,
            vendor_id=signoff.vendor_id,
            assigned_owner_id=signoff.assigned_owner_id,
            review_status=target_status,
            owner_decision_notes=formatted_notes,
            cryptographic_signature_hash=sig_hash,
            decided_at=now,
        )
        db.add(new_signoff)
        target_record = new_signoff

    db.commit()
    db.refresh(target_record)

    dispatch_notification_channels(
        owner_email=actor_owner.email_address,
        owner_preferences=actor_owner.notification_channel_preferences or {},
        subject=f"[AI Governance Signoff {decision_prefix}] {vendor.legal_name}",
        body_text=(
            f"Vendor: {vendor.legal_name} ({vendor.primary_domain})\n"
            f"Decision: {target_status.value.upper()}\n"
            f"Vendor Status: {vendor.onboarding_status.value.upper()}\n"
            f"Cryptographic Signature: {sig_hash}\n"
            f"Decision Notes: {formatted_notes}\n"
        ),
        structured_payload={
            "signoff_id": str(target_record.signoff_id),
            "assessment_id": str(target_record.assessment_id),
            "vendor_id": str(vendor.vendor_id),
            "review_status": target_status.value,
            "cryptographic_signature_hash": sig_hash,
        },
    )

    return target_record
