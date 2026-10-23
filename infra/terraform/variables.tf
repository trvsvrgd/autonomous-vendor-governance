variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS deployment region"
}

variable "environment" {
  type        = string
  default     = "prod"
  description = "Deployment environment prefix"
}

variable "s3_archive_bucket_name" {
  type        = string
  default     = "enterprise-ai-vendor-governance-archives"
  description = "Encrypted S3 bucket for ULA PDFs and vendor snapshots"
}

variable "db_instance_class" {
  type        = string
  default     = "db.m6i.large"
  description = "Amazon RDS PostgreSQL 16 instance class"
}

variable "db_master_username" {
  type        = string
  default     = "governance_admin"
  description = "Master username for RDS PostgreSQL 16"
}
