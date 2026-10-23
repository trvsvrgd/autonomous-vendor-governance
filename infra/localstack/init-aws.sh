#!/usr/bin/env bash
set -euo pipefail

echo "Provisioning LocalStack AWS resources for Autonomous AI Vendor Governance..."

awslocal s3 mb s3://enterprise-ai-vendor-governance-archives || true
awslocal s3api put-bucket-encryption \
  --bucket enterprise-ai-vendor-governance-archives \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' || true

awslocal sqs create-queue --queue-name vendor-governance-ingestion-queue || true
awslocal sqs create-queue --queue-name vendor-governance-evaluation-dlq || true
awslocal sqs create-queue --queue-name vendor-governance-evaluation-queue || true

awslocal ses verify-email-identity --email-address governance-alerts@enterprise.internal || true
awslocal ses verify-email-identity --email-address travisvreugdenhil@gmail.com || true

awslocal secretsmanager create-secret \
  --name prod/vendor-governance/gemini-credentials \
  --secret-string '{"gemini_api_key":"","vertex_project_id":"","vertex_location":"us-central1"}' || true

awslocal secretsmanager create-secret \
  --name prod/vendor-governance/notification-webhooks \
  --secret-string '{"slack_webhook_url":null,"teams_webhook_url":null,"jira_webhook_url":null}' || true

echo "LocalStack AWS resources provisioned."
