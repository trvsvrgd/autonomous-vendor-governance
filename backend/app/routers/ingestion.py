from typing import Any, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SourceType
from app.schemas import MaterialityAssessmentResponse
from app.security import verify_webhook_signature
from app.workers.doc_ingest_worker import ingest_contract_or_ula_document
from app.workers.evaluation_worker import (
    drain_evaluation_sqs_queue,
    run_materiality_evaluation_for_snapshot,
)
from app.workers.inbound_listener import (
    parse_and_process_ses_inbound_email,
    process_inbound_vendor_notification,
)

router = APIRouter(prefix="/ingestion", tags=["Multi-Channel Ingestion Engine"])


class InboundVendorBulletinWebhook(BaseModel):
    sender_email_or_domain: str
    subject: str
    body_text: str


@router.post("/vendors/{vendor_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_contract_or_ula_document(
    vendor_id: UUID,
    source_type: SourceType = Form(default=SourceType.ula_contract_pdf),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Upload PDF/DOCX contract, ULA, AI addendum, or SOC 2 report to encrypted S3 & evaluate."""
    file_bytes = await file.read()
    filename = file.filename or "uploaded_contract.pdf"

    try:
        ingest_result = ingest_contract_or_ula_document(
            db,
            vendor_id=vendor_id,
            source_type=source_type,
            filename=filename,
            file_bytes=file_bytes,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document ingestion failed: {exc}",
        ) from exc

    assessment = run_materiality_evaluation_for_snapshot(
        db,
        vendor_id=vendor_id,
        new_snapshot_id=UUID(ingest_result["new_snapshot_id"]),
        previous_snapshot_id=(
            UUID(ingest_result["previous_snapshot_id"])
            if ingest_result.get("previous_snapshot_id")
            else None
        ),
    )

    return {
        "ingestion": ingest_result,
        "assessment": MaterialityAssessmentResponse.model_validate(assessment).model_dump(
            mode="json"
        ),
    }


@router.post("/webhooks/vendor-bulletin", status_code=status.HTTP_201_CREATED)
async def receive_verified_vendor_webhook(
    request: Request,
    payload: InboundVendorBulletinWebhook,
    x_governance_signature: Optional[str] = Header(default=None),
    require_hmac: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Verified webhook receiver for inbound vendor product updates and security bulletins."""
    raw_body = await request.body()
    if require_hmac and not verify_webhook_signature(raw_body, x_governance_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Governance-Signature HMAC on inbound vendor webhook.",
        )

    try:
        result = process_inbound_vendor_notification(
            db,
            sender_email_or_domain=payload.sender_email_or_domain,
            subject=payload.subject,
            body_text=payload.body_text,
            raw_payload_bytes=raw_body,
            channel_type="webhook",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    assessment = run_materiality_evaluation_for_snapshot(
        db,
        vendor_id=UUID(result["vendor_id"]),
        new_snapshot_id=UUID(result["new_snapshot_id"]),
        previous_snapshot_id=(
            UUID(result["previous_snapshot_id"])
            if result.get("previous_snapshot_id")
            else None
        ),
    )

    return {
        "listener_result": result,
        "assessment": MaterialityAssessmentResponse.model_validate(assessment).model_dump(
            mode="json"
        ),
    }


@router.post("/ses/inbound", status_code=status.HTTP_201_CREATED)
async def receive_ses_inbound_email(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Amazon SES inbound email parser mapping sender domain to vendor_id, archiving to S3, and evaluating."""
    raw_mime_str = payload.get("raw_mime")
    try:
        if raw_mime_str:
            result = parse_and_process_ses_inbound_email(
                db, raw_mime_bytes=raw_mime_str.encode("utf-8")
            )
        else:
            result = parse_and_process_ses_inbound_email(
                db, ses_event_payload=payload
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    assessment = run_materiality_evaluation_for_snapshot(
        db,
        vendor_id=UUID(result["vendor_id"]),
        new_snapshot_id=UUID(result["new_snapshot_id"]),
        previous_snapshot_id=(
            UUID(result["previous_snapshot_id"])
            if result.get("previous_snapshot_id")
            else None
        ),
    )
    return {
        "ses_result": result,
        "assessment": MaterialityAssessmentResponse.model_validate(assessment).model_dump(
            mode="json"
        ),
    }


@router.post("/queue/drain")
def trigger_evaluation_queue_consumer(
    max_steps: int = 25,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Drain pending evaluation jobs from Amazon SQS evaluation queue up to max_step limit."""
    return drain_evaluation_sqs_queue(db, max_steps=max_steps)
