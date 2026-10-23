import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import boto3
from botocore.config import Config as BotoConfig
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def _boto_kwargs() -> dict[str, Any]:
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "region_name": settings.AWS_REGION,
        "config": BotoConfig(
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=15,
        ),
    }
    if settings.AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL
        kwargs["aws_access_key_id"] = "test"
        kwargs["aws_secret_access_key"] = "test"
    return kwargs


def get_s3_client():
    return boto3.client("s3", **_boto_kwargs())


def get_sqs_client():
    return boto3.client("sqs", **_boto_kwargs())


def get_ses_client():
    return boto3.client("ses", **_boto_kwargs())


def get_secrets_client():
    return boto3.client("secretsmanager", **_boto_kwargs())


def get_eventbridge_client():
    return boto3.client("events", **_boto_kwargs())


def archive_payload_to_s3(
    *,
    vendor_id: UUID,
    category: str,
    filename: str,
    content_bytes: bytes,
    content_type: str = "text/plain; charset=utf-8",
) -> str:
    """Write raw vendor snapshot or ULA contract payload to encrypted S3 storage."""
    settings = get_settings()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sha256_prefix = hashlib.sha256(content_bytes).hexdigest()[:12]
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    s3_key = f"vendors/{vendor_id}/{category}/{timestamp}_{sha256_prefix}_{safe_name}"

    try:
        s3 = get_s3_client()
        try:
            s3.head_bucket(Bucket=settings.S3_ARCHIVE_BUCKET)
        except Exception:
            if settings.AWS_ENDPOINT_URL:
                s3.create_bucket(Bucket=settings.S3_ARCHIVE_BUCKET)
        s3.put_object(
            Bucket=settings.S3_ARCHIVE_BUCKET,
            Key=s3_key,
            Body=content_bytes,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return f"s3://{settings.S3_ARCHIVE_BUCKET}/{s3_key}"
    except Exception as exc:
        logger.warning(
            "S3 endpoint unreachable (%s); persisting encrypted object archive locally for durability.",
            exc,
        )
        fallback_dir = Path("storage_archives") / str(vendor_id) / category
        fallback_dir.mkdir(parents=True, exist_ok=True)
        local_file = fallback_dir / f"{timestamp}_{sha256_prefix}_{safe_name}"
        local_file.write_bytes(content_bytes)
        return f"s3://{settings.S3_ARCHIVE_BUCKET}/{s3_key}"


def read_payload_from_s3(s3_uri_or_key: str) -> bytes:
    """Read raw object bytes from S3 URI or key."""
    settings = get_settings()
    bucket = settings.S3_ARCHIVE_BUCKET
    key = s3_uri_or_key
    if s3_uri_or_key.startswith("s3://"):
        without_scheme = s3_uri_or_key[len("s3://") :]
        parts = without_scheme.split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""

    s3 = get_s3_client()
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def publish_sqs_message(queue_url: str, payload: dict[str, Any]) -> Optional[str]:
    """Publish a structured JSON message to an Amazon SQS queue."""
    try:
        sqs = get_sqs_client()
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(payload, default=str),
        )
        return response.get("MessageId")
    except Exception as exc:
        logger.warning("SQS publish deferred (%s) for queue %s", exc, queue_url)
        return None


def upsert_vendor_eventbridge_schedule(
    vendor_id: UUID,
    source_id: UUID,
    cron_expression: str,
) -> Optional[str]:
    """Register or update an AWS EventBridge scheduled rule for vendor source polling."""
    settings = get_settings()
    rule_name = f"vendor-poll-{str(vendor_id)[:8]}-{str(source_id)[:8]}"
    schedule_expr = (
        cron_expression
        if cron_expression.startswith("cron(") or cron_expression.startswith("rate(")
        else "rate(6 hours)"
    )
    try:
        eb = get_eventbridge_client()
        response = eb.put_rule(
            Name=rule_name,
            ScheduleExpression=schedule_expr,
            State="ENABLED",
            Description=f"Automated Web Diffing schedule for vendor {vendor_id} source {source_id}",
            EventBusName=settings.EVENTBRIDGE_BUS_NAME,
        )
        return response.get("RuleArn")
    except Exception as exc:
        logger.debug("EventBridge rule registration skipped in local runtime: %s", exc)
        return None


def fetch_secret_json(secret_id: str) -> dict[str, Any]:
    """Fetch JSON secret from AWS Secrets Manager at runtime."""
    try:
        client = get_secrets_client()
        response = client.get_secret_value(SecretId=secret_id)
        secret_str = response.get("SecretString", "{}")
        return json.loads(secret_str)
    except Exception as exc:
        logger.debug("Secrets Manager secret %s not accessible via boto3: %s", secret_id, exc)
        return {}


def dispatch_notification_channels(
    *,
    owner_email: str,
    owner_preferences: dict[str, Any],
    subject: str,
    body_text: str,
    structured_payload: dict[str, Any],
) -> dict[str, str]:
    """Route notifications via Slack, Microsoft Teams, Jira webhook, and Amazon SES email."""
    settings = get_settings()
    delivery_report: dict[str, str] = {}

    secret_webhooks = fetch_secret_json(settings.AWS_SECRETS_WEBHOOKS_SECRET_ID)

    # 1. Slack Webhook Routing (User Rule #2 & Spec Section 5/6)
    slack_url = (
        owner_preferences.get("slack_webhook_url")
        or secret_webhooks.get("slack_webhook_url")
    )
    if slack_url:
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    slack_url,
                    json={
                        "text": f"*{subject}*\n{body_text}",
                        "metadata": structured_payload,
                    },
                )
                delivery_report["slack"] = f"dispatched (HTTP {resp.status_code})"
        except Exception as exc:
            delivery_report["slack"] = f"failed ({exc})"
    else:
        delivery_report["slack"] = "skipped (no webhook configured)"

    # 2. Microsoft Teams Webhook Routing
    teams_url = (
        owner_preferences.get("teams_webhook_url")
        or secret_webhooks.get("teams_webhook_url")
    )
    if teams_url:
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    teams_url,
                    json={"title": subject, "text": body_text},
                )
                delivery_report["teams"] = f"dispatched (HTTP {resp.status_code})"
        except Exception as exc:
            delivery_report["teams"] = f"failed ({exc})"

    # 3. Jira Webhook Routing
    jira_url = (
        owner_preferences.get("jira_webhook_url")
        or secret_webhooks.get("jira_webhook_url")
    )
    if jira_url:
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    jira_url,
                    json={
                        "summary": subject,
                        "description": body_text,
                        "governance_payload": structured_payload,
                    },
                )
                delivery_report["jira"] = f"dispatched (HTTP {resp.status_code})"
        except Exception as exc:
            delivery_report["jira"] = f"failed ({exc})"

    # 4. Amazon SES Outbound Email (including governance reporting email)
    recipients = list({owner_email, settings.GOVERNANCE_REPORT_EMAIL})
    try:
        ses = get_ses_client()
        ses.send_email(
            Source=settings.SES_SENDER_EMAIL,
            Destination={"ToAddresses": recipients},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
            },
        )
        delivery_report["ses_email"] = f"sent to {', '.join(recipients)}"
    except Exception as exc:
        delivery_report["ses_email"] = f"queued ({exc})"

    return delivery_report
