output "rds_endpoint" {
  value       = aws_db_instance.governance_postgres.endpoint
  description = "Amazon RDS PostgreSQL 16 endpoint"
}

output "s3_archive_bucket_arn" {
  value       = aws_s3_bucket.governance_archives.arn
  description = "Encrypted S3 bucket ARN for ULA and snapshot archives"
}

output "sqs_ingestion_queue_url" {
  value       = aws_sqs_queue.ingestion_queue.id
  description = "Amazon SQS Ingestion Queue URL"
}

output "sqs_evaluation_queue_url" {
  value       = aws_sqs_queue.evaluation_queue.id
  description = "Amazon SQS Gemini Evaluation Queue URL"
}

output "sqs_evaluation_dlq_url" {
  value       = aws_sqs_queue.evaluation_dlq.id
  description = "Amazon SQS Gemini Evaluation Dead Letter Queue URL"
}
