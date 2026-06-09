# Each sensitive value becomes a Secrets Manager secret; task definitions inject
# them via `secrets[].valueFrom` so plaintext never appears in the task config.
# NOTE: the secret *values* still land in Terraform state — use the encrypted S3
# backend (see versions.tf) for anything real.

resource "aws_secretsmanager_secret" "database_url" {
  name                    = "${local.name}/database-url"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = local.database_url
}

resource "aws_secretsmanager_secret" "anthropic_api_key" {
  name                    = "${local.name}/anthropic-api-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "anthropic_api_key" {
  secret_id     = aws_secretsmanager_secret.anthropic_api_key.id
  secret_string = var.anthropic_api_key
}

resource "aws_secretsmanager_secret" "voyage_api_key" {
  name                    = "${local.name}/voyage-api-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "voyage_api_key" {
  secret_id     = aws_secretsmanager_secret.voyage_api_key.id
  secret_string = var.voyage_api_key
}

resource "aws_secretsmanager_secret" "auth_secret" {
  name                    = "${local.name}/auth-secret"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "auth_secret" {
  secret_id     = aws_secretsmanager_secret.auth_secret.id
  secret_string = var.auth_secret
}

resource "aws_secretsmanager_secret" "google_client_secret" {
  name                    = "${local.name}/google-client-secret"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "google_client_secret" {
  secret_id     = aws_secretsmanager_secret.google_client_secret.id
  secret_string = var.google_client_secret
}

locals {
  # ARNs the execution role must be allowed to read.
  secret_arns = [
    aws_secretsmanager_secret.database_url.arn,
    aws_secretsmanager_secret.anthropic_api_key.arn,
    aws_secretsmanager_secret.voyage_api_key.arn,
    aws_secretsmanager_secret.auth_secret.arn,
    aws_secretsmanager_secret.google_client_secret.arn,
  ]
}
