from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessOwner
from app.schemas import BusinessOwnerCreate, BusinessOwnerResponse

router = APIRouter(prefix="/owners", tags=["Business Owners"])


@router.get("", response_model=list[BusinessOwnerResponse])
def list_business_owners(db: Session = Depends(get_db)) -> list[BusinessOwner]:
    return list(
        db.scalars(select(BusinessOwner).order_by(BusinessOwner.full_name)).all()
    )


@router.post(
    "",
    response_model=BusinessOwnerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_business_owner(
    payload: BusinessOwnerCreate,
    db: Session = Depends(get_db),
) -> BusinessOwner:
    existing = db.scalar(
        select(BusinessOwner).where(
            (BusinessOwner.email_address == payload.email_address)
            | (BusinessOwner.external_idp_subject == payload.external_idp_subject)
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Business owner with this email or IdP subject already exists.",
        )
    owner = BusinessOwner(
        external_idp_subject=payload.external_idp_subject,
        full_name=payload.full_name,
        email_address=payload.email_address,
        department=payload.department,
        notification_channel_preferences=payload.notification_channel_preferences,
        escalation_manager_id=payload.escalation_manager_id,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner


@router.patch("/{owner_id}/preferences", response_model=BusinessOwnerResponse)
def update_owner_notification_preferences(
    owner_id: UUID,
    preferences: dict[str, Any],
    db: Session = Depends(get_db),
) -> BusinessOwner:
    owner = db.scalar(select(BusinessOwner).where(BusinessOwner.owner_id == owner_id))
    if not owner:
        raise HTTPException(status_code=404, detail="Business owner not found.")
    merged = dict(owner.notification_channel_preferences or {})
    merged.update(preferences)
    owner.notification_channel_preferences = merged
    db.commit()
    db.refresh(owner)
    return owner
