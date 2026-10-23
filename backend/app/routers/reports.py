from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.finos.catalog import seed_finos_catalog
from app.reports.exporter import (
    FrameworkType,
    build_regulatory_examination_pdf,
    build_regulatory_json_export,
)
from app.schemas import FinosRiskControlResponse
from app.workers.digest_engine import (
    dispatch_non_material_digests,
    preview_non_material_digest,
)

router = APIRouter(prefix="/reports", tags=["Regulatory Reporting & Digest Engine"])


@router.get("/finos-catalog", response_model=list[FinosRiskControlResponse])
def get_finos_v2_catalog(
    db: Session = Depends(get_db),
) -> list[FinosRiskControlResponse]:
    """Return all 23 official FINOS AI Governance Framework v2 risk controls."""
    rows = seed_finos_catalog(db)
    return [FinosRiskControlResponse.model_validate(r) for r in rows]


@router.get("/export/json")
def export_regulatory_compliance_json(
    framework: FrameworkType = Query(default="unified_pack"),
    vendor_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate machine-readable JSON compliance export (SR 11-7, NIST/ISO 42001, EU AI Act, FINOS CALM)."""
    return build_regulatory_json_export(db, framework=framework, vendor_id=vendor_id)


@router.get("/export/pdf")
def export_regulatory_examination_pdf(
    framework: FrameworkType = Query(default="unified_pack"),
    vendor_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    """Generate downloadable PDF regulatory examination pack."""
    pdf_bytes = build_regulatory_examination_pdf(
        db, framework=framework, vendor_id=vendor_id
    )
    filename = f"enterprise_ai_governance_exam_pack_{framework}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/digests/preview")
def get_non_material_digest_preview(
    window_hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Preview Non-Material Digest grouped by Business Owner over prior 24h or 7d."""
    return preview_non_material_digest(db, window_hours=window_hours)


@router.post("/digests/dispatch")
def run_non_material_digest_dispatch(
    window_hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate and dispatch Non-Material Digest via Amazon SES / Slack / Teams webhooks."""
    return dispatch_non_material_digests(db, window_hours=window_hours)
