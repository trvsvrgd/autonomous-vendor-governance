from datetime import datetime, timezone
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aws_clients import archive_payload_to_s3, publish_sqs_message
from app.config import get_settings
from app.models import IngestionSource, SourceType, VendorSnapshot
from app.workers.safe_fetch import compute_normalized_sha256, safe_fetch

logger = logging.getLogger(__name__)

WEB_SOURCE_TYPES = {
    SourceType.trust_center_url,
    SourceType.release_notes_url,
    SourceType.subprocessor_url,
}


def execute_web_diff_for_source(
    db: Session,
    source_id: UUID,
    *,
    override_html_or_text: Optional[str] = None,
    force_evaluation: bool = False,
) -> dict[str, Any]:
    """Execute Automated Web Diffing Worker for a single vendor URL ingestion source.

    Fetches the public URL with AWS AVA v5.0 safe_fetch SSRF protection, strips boilerplate
    navigation DOM elements, computes SHA256 of normalized text, compares against last_sha256_hash,
    and publishes a job to the SQS evaluation queue only when the hash changes (or when forced).
    """
    settings = get_settings()
    source = db.scalar(select(IngestionSource).where(IngestionSource.source_id == source_id))
    if not source:
        raise ValueError(f"IngestionSource {source_id} not found.")

    now = datetime.now(timezone.utc)
    previous_hash = source.last_sha256_hash

    # Grab previous snapshot ID for this source if one exists
    previous_snapshot = db.scalar(
        select(VendorSnapshot)
        .where(VendorSnapshot.source_id == source.source_id)
        .order_by(VendorSnapshot.captured_at.desc())
        .limit(1)
    )

    if override_html_or_text is not None:
        from app.workers.safe_fetch import normalize_and_extract_html_text

        if "<html" in override_html_or_text.lower() or "<body" in override_html_or_text.lower():
            normalized_text = normalize_and_extract_html_text(override_html_or_text)
        else:
            normalized_text = "\n".join(
                line.strip() for line in override_html_or_text.splitlines() if line.strip()
            )
        new_hash = compute_normalized_sha256(normalized_text)
        raw_bytes = override_html_or_text.encode("utf-8")
        etag = f'"{new_hash[:16]}"'
        not_modified = False
    else:
        fetch_result = safe_fetch(
            source.target_uri_or_s3_key,
            previous_etag=None if force_evaluation else source.last_http_etag,
        )
        not_modified = fetch_result.not_modified
        normalized_text = fetch_result.normalized_text
        new_hash = fetch_result.sha256_hash
        raw_bytes = fetch_result.raw_bytes
        etag = fetch_result.etag

    source.last_polled_at = now
    if etag:
        source.last_http_etag = etag

    if not_modified or (previous_hash == new_hash and not force_evaluation):
        db.commit()
        return {
            "status": "unchanged",
            "source_id": str(source.source_id),
            "vendor_id": str(source.vendor_id),
            "sha256_hash": previous_hash,
            "sqs_published": False,
        }

    s3_uri = archive_payload_to_s3(
        vendor_id=source.vendor_id,
        category=source.source_type.value,
        filename=f"web_snapshot_{source.source_id}.txt",
        content_bytes=raw_bytes if raw_bytes else normalized_text.encode("utf-8"),
        content_type="text/plain; charset=utf-8",
    )

    snapshot = VendorSnapshot(
        source_id=source.source_id,
        vendor_id=source.vendor_id,
        raw_extracted_text=normalized_text,
        content_sha256_hash=new_hash,
        s3_archive_uri=s3_uri,
        captured_at=now,
    )
    db.add(snapshot)
    source.last_sha256_hash = new_hash
    db.commit()
    db.refresh(snapshot)

    evaluation_job = {
        "event_type": "VENDOR_SNAPSHOT_CHANGED",
        "vendor_id": str(source.vendor_id),
        "source_id": str(source.source_id),
        "previous_snapshot_id": str(previous_snapshot.snapshot_id) if previous_snapshot else None,
        "new_snapshot_id": str(snapshot.snapshot_id),
        "content_sha256_hash": new_hash,
        "captured_at": now.isoformat(),
    }
    sqs_msg_id = publish_sqs_message(settings.SQS_EVALUATION_QUEUE_URL, evaluation_job)

    return {
        "status": "changed",
        "source_id": str(source.source_id),
        "vendor_id": str(source.vendor_id),
        "previous_snapshot_id": str(previous_snapshot.snapshot_id) if previous_snapshot else None,
        "new_snapshot_id": str(snapshot.snapshot_id),
        "sha256_hash": new_hash,
        "s3_archive_uri": s3_uri,
        "sqs_published": True,
        "sqs_message_id": sqs_msg_id,
    }
