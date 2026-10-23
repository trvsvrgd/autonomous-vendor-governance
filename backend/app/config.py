from functools import lru_cache
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Application
    APP_NAME: str = "Autonomous Enterprise AI Vendor Governance Platform"
    ENVIRONMENT: str = "production"
    API_V1_PREFIX: str = "/api/v1"
    MAX_WORKER_STEPS: int = 50  # Hard max_step limit for autonomous worker loops

    # PostgreSQL 16+ Database
    DATABASE_URL: str = (
        "postgresql+psycopg://governance_admin:governance_secret_pw@localhost:5432/vendor_governance"
    )

    # AWS & Object / Queue Storage
    AWS_REGION: str = "us-east-1"
    AWS_ENDPOINT_URL: Optional[str] = None
    S3_ARCHIVE_BUCKET: str = "enterprise-ai-vendor-governance-archives"
    SQS_INGESTION_QUEUE_URL: str = (
        "http://localhost:4566/000000000000/vendor-governance-ingestion-queue"
    )
    SQS_EVALUATION_QUEUE_URL: str = (
        "http://localhost:4566/000000000000/vendor-governance-evaluation-queue"
    )
    SQS_EVALUATION_DLQ_URL: str = (
        "http://localhost:4566/000000000000/vendor-governance-evaluation-dlq"
    )
    EVENTBRIDGE_BUS_NAME: str = "default"

    # Gemini Execution Bridge (harness | api | vertex)
    GEMINI_EXECUTION_MODE: Literal["harness", "api", "vertex"] = "harness"
    GEMINI_HARNESS_COMMAND: str = "python -m app.inference.gemini_harness_cli"
    GEMINI_HARNESS_TIMEOUT_SECONDS: int = 120
    GEMINI_MODEL_ID: str = "gemini-2.5-pro"
    AWS_SECRETS_GEMINI_SECRET_ID: str = "prod/vendor-governance/gemini-credentials"
    AWS_SECRETS_WEBHOOKS_SECRET_ID: str = "prod/vendor-governance/notification-webhooks"
    VERTEX_PROJECT_ID: Optional[str] = None
    VERTEX_LOCATION: str = "us-central1"

    # Notifications & Inbound Listener
    SES_SENDER_EMAIL: str = "governance-alerts@enterprise.internal"
    GOVERNANCE_REPORT_EMAIL: str = "travisvreugdenhil@gmail.com"
    INBOUND_WEBHOOK_HMAC_SECRET: str = "enterprise-inbound-webhook-hmac-key"

    # Corporate Identity (OIDC / Cognito) & Cryptographic Signoff
    OIDC_ISSUER_URL: str = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_EnterprisePool"
    OIDC_AUDIENCE: str = "enterprise-ai-governance-client"
    OIDC_JWKS_URL: Optional[str] = None
    OIDC_VERIFY_SIGNATURE: bool = False  # Set true in deployed OIDC environments with live JWKS
    SIGNOFF_HMAC_KEY: str = "enterprise-cryptographic-signoff-integrity-key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
