terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# 1. Encrypted S3 Bucket for ULA, Contract, and Snapshot Archives
resource "aws_s3_bucket" "governance_archives" {
  bucket = var.s3_archive_bucket_name
}

resource "aws_s3_bucket_versioning" "governance_archives_versioning" {
  bucket = aws_s3_bucket.governance_archives.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "governance_archives_sse" {
  bucket = aws_s3_bucket.governance_archives.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "governance_archives_block" {
  bucket                  = aws_s3_bucket.governance_archives.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 2. Amazon SQS Queues (Ingestion Queue + Gemini Evaluation Queue + Dead Letter Queue)
resource "aws_sqs_queue" "ingestion_queue" {
  name                       = "${var.environment}-vendor-governance-ingestion-queue"
  visibility_timeout_seconds = 180
  kms_master_key_id          = "alias/aws/sqs"
}

resource "aws_sqs_queue" "evaluation_dlq" {
  name                      = "${var.environment}-vendor-governance-evaluation-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = "alias/aws/sqs"
}

resource "aws_sqs_queue" "evaluation_queue" {
  name                       = "${var.environment}-vendor-governance-evaluation-queue"
  visibility_timeout_seconds = 300
  kms_master_key_id          = "alias/aws/sqs"
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.evaluation_dlq.arn
    maxReceiveCount     = 3
  })
}

# 3. Amazon EventBridge Scheduled Rules (Web Diffing & Non-Material Digest)
resource "aws_cloudwatch_event_rule" "web_diff_schedule" {
  name                = "${var.environment}-vendor-web-diffing-schedule"
  description         = "Triggers Automated Web Diffing Worker across monitored vendor URLs"
  schedule_expression = "rate(6 hours)"
}

resource "aws_cloudwatch_event_target" "web_diff_sqs_target" {
  rule      = aws_cloudwatch_event_rule.web_diff_schedule.name
  target_id = "SendToIngestionQueue"
  arn       = aws_sqs_queue.ingestion_queue.arn
}

resource "aws_cloudwatch_event_rule" "non_material_digest_schedule" {
  name                = "${var.environment}-non-material-digest-schedule"
  description         = "Dispatches 24-hour Non-Material vendor digest per Business Owner"
  schedule_expression = "cron(0 13 * * ? *)"
}

# 4. AWS Secrets Manager Secrets for Gemini API / Vertex AI & Notification Webhooks
resource "aws_secretsmanager_secret" "gemini_credentials" {
  name        = "${var.environment}/vendor-governance/gemini-credentials"
  description = "Enterprise Gemini API key or Google Cloud Vertex AI service account JSON"
}

resource "aws_secretsmanager_secret" "notification_webhooks" {
  name        = "${var.environment}/vendor-governance/notification-webhooks"
  description = "Production Slack, Microsoft Teams, and Jira webhook URLs"
}

# 5. Amazon RDS for PostgreSQL 16 Instance
resource "aws_db_instance" "governance_postgres" {
  identifier              = "${var.environment}-vendor-governance-pg16"
  engine                  = "postgres"
  engine_version          = "16.4"
  instance_class          = var.db_instance_class
  allocated_storage       = 100
  max_allocated_storage   = 500
  storage_encrypted       = true
  db_name                 = "vendor_governance"
  username                = var.db_master_username
  manage_master_user_password = true
  multi_az                = true
  deletion_protection     = true
  skip_final_snapshot     = false
  final_snapshot_identifier = "${var.environment}-vendor-governance-final-snapshot"
}
