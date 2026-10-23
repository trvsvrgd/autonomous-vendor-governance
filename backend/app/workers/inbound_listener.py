from datetime import datetime, timezone
import email
from email import policy
from email.utils import parseaddr
import json
import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.aws_clients import archive_payload_to_s3, publish_sqs_message
from app.config import get_settings
from app.models import IngestionSource, SourceType, Vendor, VendorSnapshot
from app.workers.safe_fetch import compute_normalized_sha256, normalize_and_extract_html_text

logger = logging.getLogger(__name__)


def _extract_sender_domain(sender_address_or_domain: str) -> str:
    _, addr = parseaddr(sender_address_or_domain)
    candidate = (addr or sender_address_or_domain).strip().lower()
    if "@" in candidate:
        candidate = candidate.split("@", 1)[1]
    if candidate.startswith("www."):
        candidate = candidate[4:]
    return candidate


def _resolve_vendor_by_domain(db: Session, sender_domain: str) -> Vendor:
    cleaned = _extract_sender_domain(sender_domain)
    vendor = db.scalar(
        select(Vendor).where(func.lower(Vendor.primary_domain) == cleaned)
    )
    if vendor is None:
        # Check subdomain match (e.g., alerts.anthropic.com -> anthropic.com)
        vendors = db.scalars(select(Vendor)).all()
        for v in vendors:
            v_dom = v.primary_domain.lower().strip()
            if cleaned.endswith(f".{v_dom}") or v_dom.endswith(f".{cleaned}"):
                vendor = v
                break
    if vendor is None:
        raise ValueError(
            f"No registered vendor matched inbound sender domain '{cleaned}'."
        )
    return vendor


def process_inbound_vendor_notification(
    db: Session,
    *,
    sender_email_or_domain: str,
    subject: str,
    body_text: str,
    raw_payload_bytes: bytes,
    channel_type: str = "webhook",
) -> dict[str, Any]:
    """Inbound Vendor Notification Listener core processor.

    Maps the sender domain to the corresponding vendor_id, archives the raw payload in S3,
    saves a snapshot in vendor_snapshots, and triggers the SQS evaluation queue.
    """
    settings = get_settings()
    vendor = _resolve_vendor_by_domain(db, sender_email_or_domain)
    now = datetime.now(timezone.utc)

    if "<html" in body_text.lower() or "<body" in body_text.lower():
        normalized_body = normalize_and_extract_html_text(body_text)
    else:
        normalized_body = body_text.strip()

    full_extracted_text = f"Subject: {subject.strip()}\nFrom: {sender_email_or_domain}\n\n{normalized_body}"
    sha256_hash = compute_normalized_sha256(full_extracted_text)

    s3_archive_uri = archive_payload_to_s3(
        vendor_id=vendor.vendor_id,
        category=f"inbound_{channel_type}",
        filename=f"bulletin_{now.strftime('%Y%m%d%H%M%S')}.eml"
        if channel_type == "ses_email"
        else f"webhook_{now.strftime('%Y%m%d%H%M%S')}.json",
        content_bytes=raw_payload_bytes,
        content_type="message/rfc822" if channel_type == "ses_email" else "application/json",
    )

    source = db.scalar(
        select(IngestionSource).where(
            IngestionSource.vendor_id == vendor.vendor_id,
            IngestionSource.source_type == SourceType.inbound_email_alias,
        )
    )
    if source is None:
        source = IngestionSource(
            vendor_id=vendor.vendor_id,
            source_type=SourceType.inbound_email_alias,
            target_uri_or_s3_key=f"governance-inbox@{vendor.primary_domain}",
            polling_cron_schedule="inbound:event-driven",
            last_polled_at=now,
            last_sha256_hash=sha256_hash,
        )
        db.add(source)
        db.flush()

    previous_snapshot = db.scalar(
        select(VendorSnapshot)
        .where(VendorSnapshot.source_id == source.source_id)
        .order_by(VendorSnapshot.captured_at.desc())
        .limit(1)
    )

    source.last_polled_at = now
    source.last_sha256_hash = sha256_hash

    snapshot = VendorSnapshot(
        source_id=source.source_id,
        vendor_id=vendor.vendor_id,
        raw_extracted_text=full_extracted_text,
        content_sha256_hash=sha256_hash,
        s3_archive_uri=s3_archive_uri,
        captured_at=now,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    evaluation_job = {
        "event_type": f"INBOUND_{channel_type.upper()}_RECEIVED",
        "vendor_id": str(vendor.vendor_id),
        "source_id": str(source.source_id),
        "previous_snapshot_id": str(previous_snapshot.snapshot_id) if previous_snapshot else None,
        "new_snapshot_id": str(snapshot.snapshot_id),
        "content_sha256_hash": sha256_hash,
        "captured_at": now.isoformat(),
    }
    sqs_msg_id = publish_sqs_message(settings.SQS_EVALUATION_QUEUE_URL, evaluation_job)

    return {
        "status": "processed",
        "vendor_id": str(vendor.vendor_id),
        "vendor_legal_name": vendor.legal_name,
        "source_id": str(source.source_id),
        "previous_snapshot_id": str(previous_snapshot.snapshot_id) if previous_snapshot else None,
        "new_snapshot_id": str(snapshot.snapshot_id),
        "s3_archive_uri": s3_archive_uri,
        "content_sha256_hash": sha256_hash,
        "sqs_message_id": sqs_msg_id,
    }


def parse_and_process_ses_inbound_email(
    db: Session,
    *,
    raw_mime_bytes: Optional[bytes] = None,
    ses_event_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Parse an Amazon SES inbound MIME email or SNS-wrapped SES inbound notification."""
    if raw_mime_bytes:
        msg = email.message_from_bytes(raw_mime_bytes, policy=policy.default)
        sender = str(msg.get("From", ""))
        subject = str(msg.get("Subject", "Vendor Product & Governance Update"))
        body_parts: list[str] = []
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ("text/plain", "text/html"):
                    try:
                        body_parts.append(part.get_content())
                    except Exception:
                        payload_bytes = part.get_payload(decode=True) or b""
                        body_parts.append(payload_bytes.decode("utf-8", errors="replace"))
        else:
            try:
                body_parts.append(msg.get_content())
            except Exception:
                payload_bytes = msg.get_payload(decode=True) or b""
                body_parts.append(payload_bytes.decode("utf-8", errors="replace"))

        return process_inbound_vendor_notification(
            db,
            sender_email_or_domain=sender,
            subject=subject,
            body_text="\n\n".join(body_parts),
            raw_payload_bytes=raw_mime_bytes,
            channel_type="ses_email",
        )

    if ses_event_payload:
        mail_obj = ses_event_payload.get("mail") or {}
        common_headers = mail_obj.get("commonHeaders") or {}
        from_list = common_headers.get("from") or [mail_obj.get("source", "")]
        sender = from_list[0] if from_list else str(ses_event_payload.get("sender", ""))
        subject = common_headers.get("subject") or str(
            ses_event_payload.get("subject", "Vendor Governance Bulletin")
        )
        content = str(
            ses_event_payload.get("content")
            or ses_event_payload.get("body")
            or json.dumps(ses_event_payload)
        )
        return process_inbound_vendor_notification(
            db,
            sender_email_or_domain=sender,
            subject=subject,
            body_text=content,
            raw_payload_bytes=json.dumps(ses_event_payload).encode("utf-8"),
            channel_type="ses_email",
        )

    raise ValueError("Either raw_mime_bytes or ses_event_payload is required.")
