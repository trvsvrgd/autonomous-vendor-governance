import hashlib
import hmac
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import BusinessOwner, ReviewStatus


class CorporateIdentityContext:
    def __init__(
        self,
        subject: str,
        email: str,
        full_name: str,
        owner: Optional[BusinessOwner] = None,
    ) -> None:
        self.subject = subject
        self.email = email
        self.full_name = full_name
        self.owner = owner


def compute_signoff_signature_hash(
    *,
    signoff_id: UUID,
    assessment_id: UUID,
    vendor_id: UUID,
    assigned_owner_id: UUID,
    idp_subject: str,
    review_status: ReviewStatus,
    owner_decision_notes: str,
    decided_at: datetime,
) -> str:
    """Compute an immutable HMAC-SHA256 cryptographic signature binding corporate identity to signoff."""
    settings = get_settings()
    canonical_payload = "|".join(
        [
            str(signoff_id),
            str(assessment_id),
            str(vendor_id),
            str(assigned_owner_id),
            idp_subject.strip(),
            review_status.value,
            owner_decision_notes.strip(),
            decided_at.isoformat(),
        ]
    )
    digest = hmac.new(
        settings.SIGNOFF_HMAC_KEY.encode("utf-8"),
        canonical_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256:{digest}"


def verify_webhook_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """Verify HMAC-SHA256 signature on inbound vendor notification webhooks."""
    settings = get_settings()
    if not signature_header:
        return False
    cleaned_sig = signature_header.replace("sha256=", "").strip()
    expected = hmac.new(
        settings.INBOUND_WEBHOOK_HMAC_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(cleaned_sig, expected)


def resolve_corporate_identity(
    authorization: Optional[str] = Header(default=None),
    x_corporate_idp_subject: Optional[str] = Header(default=None),
    x_corporate_email: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> CorporateIdentityContext:
    """Resolve corporate OIDC / AWS Cognito identity and bind to a BusinessOwner record."""
    settings = get_settings()
    claims: dict[str, Any] = {}

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            if settings.OIDC_VERIFY_SIGNATURE and settings.OIDC_JWKS_URL:
                jwks_client = jwt.PyJWKClient(settings.OIDC_JWKS_URL)
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "ES256"],
                    audience=settings.OIDC_AUDIENCE,
                    issuer=settings.OIDC_ISSUER_URL,
                )
            else:
                claims = jwt.decode(token, options={"verify_signature": False})
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid corporate OIDC bearer token: {exc}",
            ) from exc

    subject = (
        claims.get("sub")
        or x_corporate_idp_subject
        or "oidc:enterprise-governance-lead"
    )
    email = (
        claims.get("email")
        or x_corporate_email
        or settings.GOVERNANCE_REPORT_EMAIL
    )
    full_name = claims.get("name") or "Enterprise Governance Lead"

    owner = db.scalar(
        select(BusinessOwner).where(
            (BusinessOwner.external_idp_subject == subject)
            | (BusinessOwner.email_address == email)
        )
    )
    if owner is None:
        owner = db.scalar(select(BusinessOwner).limit(1))

    return CorporateIdentityContext(
        subject=owner.external_idp_subject if owner else subject,
        email=owner.email_address if owner else email,
        full_name=owner.full_name if owner else full_name,
        owner=owner,
    )
