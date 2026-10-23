from contextlib import asynccontextmanager
import logging
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.finos.catalog import seed_finos_catalog
from app.models import FinosRiskControl, Vendor
from app.routers import ingestion, owners, reports, triage, vendors

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_finos_catalog(db)
    logger.info(
        "Initialized %s (GEMINI_EXECUTION_MODE=%s)",
        settings.APP_NAME,
        settings.GEMINI_EXECUTION_MODE,
    )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description=(
        "Continuously updating enterprise AI vendor governance platform aligned with "
        "FINOS AI Governance Framework v2, FINOS CALM 1.0, and AWS Agentic Value Accelerator v5.0 Govern."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(owners.router, prefix=settings.API_V1_PREFIX)
app.include_router(vendors.router, prefix=settings.API_V1_PREFIX)
app.include_router(triage.router, prefix=settings.API_V1_PREFIX)
app.include_router(ingestion.router, prefix=settings.API_V1_PREFIX)
app.include_router(reports.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["System"])
def system_healthcheck(db: Session = Depends(get_db)) -> dict[str, Any]:
    finos_count = int(db.scalar(select(func.count(FinosRiskControl.risk_id))) or 0)
    vendor_count = int(db.scalar(select(func.count(Vendor.vendor_id))) or 0)
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "gemini_execution_mode": settings.GEMINI_EXECUTION_MODE,
        "gemini_model_id": settings.GEMINI_MODEL_ID,
        "finos_v2_controls_seeded": finos_count,
        "vendors_monitored": vendor_count,
        "max_worker_steps": settings.MAX_WORKER_STEPS,
    }
