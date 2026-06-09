provider "aws" {
  region  = var.region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = {
      Project   = var.project
      Env       = var.env
      ManagedBy = "terraform"
    }
  }
}

locals {
  name = "${var.project}-${var.env}"

  # The app's single DATABASE_URL, composed from the RDS endpoint + password so
  # backend/worker/migrate need no code change (config.py reads DATABASE_URL).
  database_url = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.this.address}:5432/${var.db_name}"

  # Public base URL the frontend advertises to Google (OAuth redirect origin).
  app_url = var.acm_certificate_arn != "" ? "https://${aws_lb.this.dns_name}" : "http://${aws_lb.this.dns_name}"
}

data "aws_availability_zones" "available" {
  state = "available"
}
