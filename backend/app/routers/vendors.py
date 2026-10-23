import csv
import io
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.aws_clients import publish_sqs_message, upsert_vendor_eventbridge_schedule
from app.config import get_settings
from app.database import get_db
from app.models import (
    AutonomyClassification,
    BusinessOwner,
    GovernanceSignoff,
    HostingTopology,
    IngestionSource,
    MaterialityAssessment,
    MaterialityLevel,
    OnboardingStatus,
    ReviewStatus,
    RiskTier,
    SourceType,
    Vendor,
    VendorAICapability,
    VendorSnapshot,
)
from app.schemas import (
    BusinessOwnerResponse,
    CommandCenterKPIs,
    CommandCenterResponse,
    IngestionSourceCreate,
    IngestionSourceResponse,
    MaterialityAssessmentResponse,
    VendorAICapabilityResponse,
    VendorDetailResponse,
    VendorOnboardRequest,
    VendorSnapshotResponse,
    VendorSummaryRow,
    GovernanceSignoffResponse,
)
from app.workers.evaluation_worker import run_materiality_evaluation_for_snapshot
from app.workers.web_diff_worker import WEB_SOURCE_TYPES, execute_web_diff_for_source

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vendors", tags=["Vendors & Onboarding"])


class ForceCrawlEvaluateRequest(BaseModel):
    source_id: Optional[UUID] = None
    override_snapshot_text: Optional[str] = None


def _build_vendor_summary_row(vendor: Vendor) -> VendorSummaryRow:
    active_material_alerts = 0
    latest_signoff_status: Optional[ReviewStatus] = None
    latest_assessment_at = None

    sorted_assessments = sorted(
        vendor.assessments, key=lambda a: a.evaluated_at, reverse=True
    )
    if sorted_assessments:
        latest_assessment_at = sorted_assessments[0].evaluated_at

    sorted_signoffs = sorted(
        vendor.signoffs, key=lambda s: s.created_at, reverse=True
    )
    if sorted_signoffs:
        latest_signoff_status = sorted_signoffs[0].review_status

    assessment_map = {a.assessment_id: a for a in vendor.assessments}
    for s in vendor.signoffs:
        linked_a = assessment_map.get(s.assessment_id)
        if (
            s.review_status == ReviewStatus.awaiting_review
            and linked_a
            and linked_a.materiality_level == MaterialityLevel.material
        ):
            active_material_alerts += 1

    return VendorSummaryRow(
        vendor_id=vendor.vendor_id,
        legal_name=vendor.legal_name,
        primary_domain=vendor.primary_domain,
        onboarding_status=vendor.onboarding_status,
        risk_tier=vendor.risk_tier,
        primary_owner=BusinessOwnerResponse.model_validate(vendor.primary_owner),
        secondary_owner=(
            BusinessOwnerResponse.model_validate(vendor.secondary_owner)
            if vendor.secondary_owner
            else None
        ),
        ai_capabilities=[
            VendorAICapabilityResponse.model_validate(c)
            for c in vendor.ai_capabilities
        ],
        active_material_alerts_count=active_material_alerts,
        latest_review_status=latest_signoff_status,
        latest_assessment_at=latest_assessment_at,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
    )


@router.get("", response_model=CommandCenterResponse)
def list_vendors_command_center(
    risk_tier: Optional[RiskTier] = Query(default=None),
    owner_id: Optional[UUID] = Query(default=None),
    foundation_model_family: Optional[str] = Query(default=None),
    autonomy_classification: Optional[AutonomyClassification] = Query(default=None),
    review_status: Optional[ReviewStatus] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> CommandCenterResponse:
    """Enterprise Vendor Command Center grid with server-side filtering and live KPIs."""
    all_vendors = list(
        db.scalars(
            select(Vendor)
            .options(
                selectinload(Vendor.primary_owner),
                selectinload(Vendor.secondary_owner),
                selectinload(Vendor.ai_capabilities),
                selectinload(Vendor.assessments),
                selectinload(Vendor.signoffs),
            )
            .order_by(Vendor.legal_name)
        ).all()
    )

    total_vendors_monitored = len(all_vendors)
    total_snapshots = int(
        db.scalar(select(func.count(VendorSnapshot.snapshot_id))) or 0
    )

    active_material_alerts = int(
        db.scalar(
            select(func.count(GovernanceSignoff.signoff_id))
            .join(
                MaterialityAssessment,
                GovernanceSignoff.assessment_id == MaterialityAssessment.assessment_id,
            )
            .where(
                GovernanceSignoff.review_status == ReviewStatus.awaiting_review,
                MaterialityAssessment.materiality_level == MaterialityLevel.material,
            )
        )
        or 0
    )

    autonomous_vendor_count = sum(
        1
        for v in all_vendors
        if any(
            c.autonomy_classification
            in (
                AutonomyClassification.tool_calling_agent,
                AutonomyClassification.multi_agent_autonomous,
            )
            or c.mcp_or_a2a_enabled
            for c in v.ai_capabilities
        )
    )
    autonomous_pct = (
        round((autonomous_vendor_count / total_vendors_monitored) * 100.0, 1)
        if total_vendors_monitored > 0
        else 0.0
    )
    critical_or_high_count = sum(
        1 for v in all_vendors if v.risk_tier in (RiskTier.critical, RiskTier.high)
    )

    # Apply server-side filters
    filtered_rows: list[VendorSummaryRow] = []
    for v in all_vendors:
        if risk_tier and v.risk_tier != risk_tier:
            continue
        if owner_id and v.primary_owner_id != owner_id and v.secondary_owner_id != owner_id:
            continue
        if foundation_model_family:
            q_model = foundation_model_family.strip().lower()
            if not any(q_model in c.foundation_model_family.lower() for c in v.ai_capabilities):
                continue
        if autonomy_classification:
            if not any(c.autonomy_classification == autonomy_classification for c in v.ai_capabilities):
                continue
        if search:
            q = search.strip().lower()
            haystack = " ".join(
                [
                    v.legal_name.lower(),
                    v.primary_domain.lower(),
                    v.primary_owner.full_name.lower() if v.primary_owner else "",
                    " ".join(c.foundation_model_family.lower() for c in v.ai_capabilities),
                    " ".join(c.product_module_name.lower() for c in v.ai_capabilities),
                ]
            )
            if q not in haystack:
                continue

        summary_row = _build_vendor_summary_row(v)
        if review_status and summary_row.latest_review_status != review_status:
            continue
        filtered_rows.append(summary_row)

    return CommandCenterResponse(
        kpis=CommandCenterKPIs(
            total_vendors_monitored=total_vendors_monitored,
            active_material_alerts_awaiting_signoff=active_material_alerts,
            autonomous_agent_vendor_percentage=autonomous_pct,
            critical_or_high_risk_vendors=critical_or_high_count,
            total_snapshots_archived=total_snapshots,
        ),
        vendors=filtered_rows,
        total_count=len(filtered_rows),
    )


@router.post("", response_model=VendorSummaryRow, status_code=status.HTTP_201_CREATED)
def onboard_single_vendor(
    payload: VendorOnboardRequest,
    db: Session = Depends(get_db),
) -> VendorSummaryRow:
    """Transactional single-vendor onboarding API. Schedules EventBridge rules & baseline collection."""
    settings = get_settings()
    existing = db.scalar(
        select(Vendor).where(
            func.lower(Vendor.primary_domain) == payload.primary_domain.strip().lower()
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Vendor with domain '{payload.primary_domain}' is already registered.",
        )

    owner = db.scalar(
        select(BusinessOwner).where(BusinessOwner.owner_id == payload.primary_owner_id)
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Primary Business Owner not found.")

    vendor = Vendor(
        legal_name=payload.legal_name.strip(),
        primary_domain=payload.primary_domain.strip().lower(),
        onboarding_status=payload.onboarding_status,
        risk_tier=payload.risk_tier,
        primary_owner_id=payload.primary_owner_id,
        secondary_owner_id=payload.secondary_owner_id,
    )
    db.add(vendor)
    db.flush()

    for cap_in in payload.ai_capabilities:
        cap = VendorAICapability(
            vendor_id=vendor.vendor_id,
            product_module_name=cap_in.product_module_name,
            foundation_model_family=cap_in.foundation_model_family,
            model_provider=cap_in.model_provider,
            hosting_topology=cap_in.hosting_topology,
            autonomy_classification=cap_in.autonomy_classification,
            mcp_or_a2a_enabled=cap_in.mcp_or_a2a_enabled,
            trains_on_customer_data=cap_in.trains_on_customer_data,
            data_retention_days=cap_in.data_retention_days,
        )
        db.add(cap)

    created_sources: list[IngestionSource] = []
    for src_in in payload.ingestion_sources:
        src = IngestionSource(
            vendor_id=vendor.vendor_id,
            source_type=src_in.source_type,
            target_uri_or_s3_key=src_in.target_uri_or_s3_key,
            polling_cron_schedule=src_in.polling_cron_schedule,
        )
        db.add(src)
        db.flush()
        created_sources.append(src)
        upsert_vendor_eventbridge_schedule(
            vendor.vendor_id, src.source_id, src.polling_cron_schedule
        )

    db.commit()

    # Schedule baseline collection jobs across attached sources
    if payload.trigger_immediate_baseline:
        for src in created_sources:
            publish_sqs_message(
                settings.SQS_INGESTION_QUEUE_URL,
                {
                    "event_type": "BASELINE_INGESTION_JOB",
                    "vendor_id": str(vendor.vendor_id),
                    "source_id": str(src.source_id),
                    "source_type": src.source_type.value,
                    "target_uri": src.target_uri_or_s3_key,
                },
            )
            if src.source_type in WEB_SOURCE_TYPES:
                try:
                    diff_res = execute_web_diff_for_source(
                        db, src.source_id, force_evaluation=True
                    )
                    if diff_res.get("new_snapshot_id"):
                        run_materiality_evaluation_for_snapshot(
                            db,
                            vendor_id=vendor.vendor_id,
                            new_snapshot_id=UUID(diff_res["new_snapshot_id"]),
                        )
                except Exception as exc:
                    logger.info(
                        "Baseline live URL crawl for %s deferred to background worker: %s",
                        src.target_uri_or_s3_key,
                        exc,
                    )

    refreshed = db.scalar(
        select(Vendor)
        .options(
            selectinload(Vendor.primary_owner),
            selectinload(Vendor.secondary_owner),
            selectinload(Vendor.ai_capabilities),
            selectinload(Vendor.assessments),
            selectinload(Vendor.signoffs),
        )
        .where(Vendor.vendor_id == vendor.vendor_id)
    )
    return _build_vendor_summary_row(refreshed)


@router.post("/bulk-csv", status_code=status.HTTP_201_CREATED)
async def bulk_onboard_vendors_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Bulk Intake CSV Upload API. Registers multiple vendors transactionally and initiates baseline evaluations."""
    settings = get_settings()
    raw_bytes = await file.read()
    text_content = raw_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text_content))

    created_vendors = 0
    updated_vendors = 0
    baseline_assessments_created = 0
    results: list[dict[str, Any]] = []

    for idx, row in enumerate(reader, start=1):
        if idx > settings.MAX_WORKER_STEPS * 10:
            break
        legal_name = (row.get("legal_name") or "").strip()
        primary_domain = (row.get("primary_domain") or "").strip().lower()
        if not legal_name or not primary_domain:
            continue

        owner_email = (
            row.get("owner_email") or settings.GOVERNANCE_REPORT_EMAIL
        ).strip()
        owner_name = (row.get("owner_name") or "Enterprise AI Risk Lead").strip()
        owner_dept = (row.get("owner_department") or "Enterprise Risk & Compliance").strip()

        owner = db.scalar(
            select(BusinessOwner).where(BusinessOwner.email_address == owner_email)
        )
        if not owner:
            owner = BusinessOwner(
                external_idp_subject=f"oidc:{owner_email}",
                full_name=owner_name,
                email_address=owner_email,
                department=owner_dept,
                notification_channel_preferences={
                    "email_enabled": True,
                    "digest_frequency": "24h",
                },
            )
            db.add(owner)
            db.flush()

        risk_str = (row.get("risk_tier") or "high").strip().lower()
        risk_tier = (
            RiskTier(risk_str)
            if risk_str in RiskTier._value2member_map_
            else RiskTier.high
        )

        vendor = db.scalar(
            select(Vendor).where(func.lower(Vendor.primary_domain) == primary_domain)
        )
        if not vendor:
            vendor = Vendor(
                legal_name=legal_name,
                primary_domain=primary_domain,
                onboarding_status=OnboardingStatus.active,
                risk_tier=risk_tier,
                primary_owner_id=owner.owner_id,
            )
            db.add(vendor)
            db.flush()
            created_vendors += 1
        else:
            vendor.legal_name = legal_name
            vendor.risk_tier = risk_tier
            updated_vendors += 1

        # Add capability if provided
        mod_name = (row.get("product_module_name") or f"{legal_name} Core AI Suite").strip()
        model_family = (row.get("foundation_model_family") or "Gemini 2.5 Pro").strip()
        model_provider = (row.get("model_provider") or "Google DeepMind").strip()
        topology_str = (row.get("hosting_topology") or "vendor_hosted").strip().lower()
        topology = (
            HostingTopology(topology_str)
            if topology_str in HostingTopology._value2member_map_
            else HostingTopology.vendor_hosted
        )
        autonomy_str = (row.get("autonomy_classification") or "assistive_copilot").strip().lower()
        autonomy = (
            AutonomyClassification(autonomy_str)
            if autonomy_str in AutonomyClassification._value2member_map_
            else AutonomyClassification.assistive_copilot
        )
        mcp_enabled = str(row.get("mcp_or_a2a_enabled") or "false").strip().lower() in (
            "true",
            "1",
            "yes",
        )
        trains_data = str(row.get("trains_on_customer_data") or "false").strip().lower() in (
            "true",
            "1",
            "yes",
        )
        retention_days = int(row.get("data_retention_days") or 0)

        existing_cap = db.scalar(
            select(VendorAICapability).where(
                VendorAICapability.vendor_id == vendor.vendor_id,
                VendorAICapability.product_module_name == mod_name,
            )
        )
        if not existing_cap:
            db.add(
                VendorAICapability(
                    vendor_id=vendor.vendor_id,
                    product_module_name=mod_name,
                    foundation_model_family=model_family,
                    model_provider=model_provider,
                    hosting_topology=topology,
                    autonomy_classification=autonomy,
                    mcp_or_a2a_enabled=mcp_enabled,
                    trains_on_customer_data=trains_data,
                    data_retention_days=retention_days,
                )
            )
            db.flush()

        trust_url = (
            row.get("trust_center_url") or f"https://{primary_domain}/security/trust-center"
        ).strip()
        source = db.scalar(
            select(IngestionSource).where(
                IngestionSource.vendor_id == vendor.vendor_id,
                IngestionSource.target_uri_or_s3_key == trust_url,
            )
        )
        if not source:
            source = IngestionSource(
                vendor_id=vendor.vendor_id,
                source_type=SourceType.trust_center_url,
                target_uri_or_s3_key=trust_url,
                polling_cron_schedule="0 */6 * * *",
            )
            db.add(source)
            db.flush()
            upsert_vendor_eventbridge_schedule(
                vendor.vendor_id, source.source_id, source.polling_cron_schedule
            )

        db.commit()

        baseline_text = (row.get("baseline_disclosure_text") or "").strip()
        if not baseline_text:
            baseline_text = (
                f"{legal_name} Trust Center & AI Governance Disclosure ({primary_domain}). "
                f"Module: {mod_name}. Foundation Model: {model_family} ({model_provider}) hosted on {topology.value}. "
                f"Autonomy classification: {autonomy.value}. "
                f"{'Model Context Protocol (MCP) and A2A enabled.' if mcp_enabled else 'Standard API boundary.'} "
                f"{'Trains on customer data.' if trains_data else 'Zero data retention; does not train on customer data.'} "
                f"Data retention period: {retention_days} days."
            )

        diff_res = execute_web_diff_for_source(
            db,
            source.source_id,
            override_html_or_text=baseline_text,
            force_evaluation=True,
        )
        if diff_res.get("new_snapshot_id"):
            run_materiality_evaluation_for_snapshot(
                db,
                vendor_id=vendor.vendor_id,
                new_snapshot_id=UUID(diff_res["new_snapshot_id"]),
            )
            baseline_assessments_created += 1

        results.append(
            {
                "vendor_id": str(vendor.vendor_id),
                "legal_name": vendor.legal_name,
                "primary_domain": vendor.primary_domain,
            }
        )

    return {
        "status": "completed",
        "created_vendors": created_vendors,
        "updated_vendors": updated_vendors,
        "baseline_assessments_created": baseline_assessments_created,
        "vendors": results,
    }


@router.get("/{vendor_id}", response_model=VendorDetailResponse)
def get_vendor_detail_workspace(
    vendor_id: UUID,
    db: Session = Depends(get_db),
) -> VendorDetailResponse:
    """Vendor Detail and Source Configuration Workspace drill-down."""
    vendor = db.scalar(
        select(Vendor)
        .options(
            selectinload(Vendor.primary_owner),
            selectinload(Vendor.secondary_owner),
            selectinload(Vendor.ai_capabilities),
            selectinload(Vendor.ingestion_sources),
            selectinload(Vendor.snapshots),
            selectinload(Vendor.assessments),
            selectinload(Vendor.signoffs),
        )
        .where(Vendor.vendor_id == vendor_id)
    )
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found.")

    return VendorDetailResponse(
        vendor=_build_vendor_summary_row(vendor),
        ingestion_sources=[
            IngestionSourceResponse.model_validate(s)
            for s in sorted(vendor.ingestion_sources, key=lambda x: x.created_at)
        ],
        snapshots=[
            VendorSnapshotResponse.model_validate(sn)
            for sn in sorted(vendor.snapshots, key=lambda x: x.captured_at, reverse=True)
        ],
        assessments=[
            MaterialityAssessmentResponse.model_validate(a)
            for a in sorted(vendor.assessments, key=lambda x: x.evaluated_at, reverse=True)
        ],
        signoffs=[
            GovernanceSignoffResponse.model_validate(sg)
            for sg in sorted(vendor.signoffs, key=lambda x: x.created_at, reverse=True)
        ],
    )


@router.post(
    "/{vendor_id}/sources",
    response_model=IngestionSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_vendor_ingestion_source(
    vendor_id: UUID,
    payload: IngestionSourceCreate,
    db: Session = Depends(get_db),
) -> IngestionSource:
    vendor = db.scalar(select(Vendor).where(Vendor.vendor_id == vendor_id))
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found.")

    source = IngestionSource(
        vendor_id=vendor_id,
        source_type=payload.source_type,
        target_uri_or_s3_key=payload.target_uri_or_s3_key,
        polling_cron_schedule=payload.polling_cron_schedule,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    upsert_vendor_eventbridge_schedule(
        vendor_id, source.source_id, source.polling_cron_schedule
    )
    return source


@router.post("/{vendor_id}/crawl-and-evaluate")
def force_live_crawl_and_gemini_evaluation(
    vendor_id: UUID,
    payload: ForceCrawlEvaluateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Trigger an immediate live crawl (or snapshot diff) and Gemini harness evaluation."""
    vendor = db.scalar(
        select(Vendor)
        .options(selectinload(Vendor.ingestion_sources))
        .where(Vendor.vendor_id == vendor_id)
    )
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found.")

    target_source: Optional[IngestionSource] = None
    if payload.source_id:
        target_source = db.scalar(
            select(IngestionSource).where(
                IngestionSource.source_id == payload.source_id,
                IngestionSource.vendor_id == vendor_id,
            )
        )
    elif vendor.ingestion_sources:
        web_sources = [
            s for s in vendor.ingestion_sources if s.source_type in WEB_SOURCE_TYPES
        ]
        target_source = web_sources[0] if web_sources else vendor.ingestion_sources[0]

    if not target_source:
        target_source = IngestionSource(
            vendor_id=vendor.vendor_id,
            source_type=SourceType.trust_center_url,
            target_uri_or_s3_key=f"https://{vendor.primary_domain}/trust",
            polling_cron_schedule="0 */6 * * *",
        )
        db.add(target_source)
        db.commit()
        db.refresh(target_source)

    try:
        diff_res = execute_web_diff_for_source(
            db,
            target_source.source_id,
            override_html_or_text=payload.override_snapshot_text,
            force_evaluation=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Live crawl / SSRF safe_fetch failed: {exc}",
        ) from exc

    new_snap_id = diff_res.get("new_snapshot_id")
    prev_snap_id = diff_res.get("previous_snapshot_id")
    if not new_snap_id:
        return {
            "status": "no_change",
            "crawl_result": diff_res,
        }

    assessment = run_materiality_evaluation_for_snapshot(
        db,
        vendor_id=vendor.vendor_id,
        new_snapshot_id=UUID(new_snap_id),
        previous_snapshot_id=UUID(prev_snap_id) if prev_snap_id else None,
    )

    return {
        "status": "evaluated",
        "crawl_result": diff_res,
        "assessment": MaterialityAssessmentResponse.model_validate(assessment).model_dump(
            mode="json"
        ),
    }
