output "alb_dns_name" {
  description = "Public hostname for the app."
  value       = aws_lb.this.dns_name
}

output "app_url" {
  description = "Base URL the frontend advertises (set the Google redirect URI to <app_url>/api/auth/callback)."
  value       = local.app_url
}

output "ecr_backend_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_repository_url" {
  value = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "sqs_ingest_queue_url" {
  value = aws_sqs_queue.ingest.url
}

output "docs_bucket" {
  description = "Drop documents here; ObjectCreated/Removed events drive the worker."
  value       = aws_s3_bucket.docs.bucket
}

output "rds_endpoint" {
  value = aws_db_instance.this.address
}

# Convenience: the one-off DB migration command (run after the first image push).
output "migrate_run_task_command" {
  value = join(" ", [
    "aws ecs run-task",
    "--cluster ${aws_ecs_cluster.this.name}",
    "--task-definition ${aws_ecs_task_definition.migrate.family}",
    "--launch-type FARGATE",
    "--network-configuration 'awsvpcConfiguration={subnets=[${join(",", module.vpc.private_subnets)}],securityGroups=[${aws_security_group.ecs_tasks.id}],assignPublicIp=DISABLED}'",
    "--region ${var.region}",
  ])
}
