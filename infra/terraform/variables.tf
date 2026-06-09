# ── Identity / provider ──────────────────────────────────────────────────────
variable "project" {
  type        = string
  default     = "rag"
  description = "Short name used as the prefix for every resource."
}

variable "env" {
  type        = string
  default     = "prod"
  description = "Environment name (prod, staging, ...)."
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type        = string
  default     = ""
  description = "Optional named AWS CLI profile; empty uses the default credential chain."
}

# ── Networking ───────────────────────────────────────────────────────────────
variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

# ── Images ───────────────────────────────────────────────────────────────────
variable "image_tag" {
  type        = string
  default     = "latest"
  description = "Tag pushed to both ECR repos and run by every service."
}

# ── Database ─────────────────────────────────────────────────────────────────
variable "db_name" {
  type    = string
  default = "rag"
}

variable "db_username" {
  type    = string
  default = "rag"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

# ── Service sizing ───────────────────────────────────────────────────────────
variable "task_cpu" {
  type        = number
  default     = 256
  description = "Fargate CPU units per task (256 = 0.25 vCPU)."
}

variable "task_memory" {
  type    = number
  default = 512
}

variable "desired_count" {
  type        = number
  default     = 1
  description = "Replica count for the backend and frontend services."
}

# ── Auth (must match the backend/frontend env contract) ──────────────────────
variable "auth_enabled" {
  type    = bool
  default = false
}

variable "google_oauth_client_id" {
  type    = string
  default = ""
}

variable "google_hosted_domain" {
  type    = string
  default = ""
}

# ── HTTPS (optional) ─────────────────────────────────────────────────────────
variable "acm_certificate_arn" {
  type        = string
  default     = ""
  description = "If set, adds an HTTPS:443 listener and redirects HTTP to it."
}

# ── Secrets (sensitive — never commit a filled tfvars; prefer TF_VAR_*) ───────
variable "db_password" {
  type      = string
  sensitive = true
}

variable "anthropic_api_key" {
  type      = string
  sensitive = true
}

variable "voyage_api_key" {
  type      = string
  sensitive = true
}

variable "auth_secret" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Session-cookie encryption secret for the frontend (openssl rand -base64 32). Required only when auth_enabled."
}

variable "google_client_secret" {
  type      = string
  sensitive = true
  default   = ""
}
