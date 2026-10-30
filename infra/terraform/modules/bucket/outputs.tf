output "id" {
  description = "Bucket name."
  value       = aws_s3_bucket.this.bucket
}

output "arn" {
  description = "Bucket ARN (objects are `<arn>/*`)."
  value       = aws_s3_bucket.this.arn
}
