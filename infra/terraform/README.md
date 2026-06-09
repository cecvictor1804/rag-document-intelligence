# Infrastructure (Phase 4) — AWS on ECS Fargate

Terraform for the production deployment. It provisions a VPC (2 AZs, single NAT),
RDS Postgres 16 (pgvector), an S3 docs bucket wired to SQS, two ECR repos,
Secrets Manager, and an ECS Fargate cluster running three services:

| Service    | Ingress            | Command                              |
|------------|--------------------|--------------------------------------|
| `frontend` | public ALB (:80/443) | `node server.js` (Next standalone) |
| `backend`  | private, Service Connect `backend:8000` | `uvicorn app.main:app` |
| `worker`   | none (long-polls SQS) | `python -m ingestion.pipeline.worker` |

The browser only reaches the **frontend**; it proxies to the **backend** over ECS
Service Connect, so the API is never public. A one-off `migrate` task definition
runs the schema migration.

> **Heads-up:** secret *values* (DB password, API keys) are stored in Terraform
> state. Use the encrypted S3 backend stub in `versions.tf` for anything real,
> and pass secrets as `TF_VAR_*` env vars rather than a committed `.tfvars`.

## Prerequisites

- Terraform >= 1.6, the AWS CLI, and Docker, all authenticated to the target
  account/region.
- API keys: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`.

## Deploy

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars     # edit non-secret values

# Secrets via env (preferred over writing them into the tfvars):
export TF_VAR_db_password=$(openssl rand -base64 24)
export TF_VAR_anthropic_api_key=sk-ant-...
export TF_VAR_voyage_api_key=pa-...
# Only if auth_enabled = true:
export TF_VAR_auth_secret=$(openssl rand -base64 32)
export TF_VAR_google_client_secret=...

terraform init
terraform apply        # creates everything; the 3 services stay unhealthy until images exist
```

`apply` prints the ECR repo URLs, the cluster name, the ALB DNS, the docs bucket,
and a ready-to-run `migrate_run_task_command`.

### Build & push images, then migrate

From the repo root, with `<acct>`, `<region>`, and the ECR URLs from the outputs:

```bash
aws ecr get-login-password --region <region> \
  | docker login --username AWS --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com

# Backend (+ ingestion + migrate share this image)
docker build -t <ecr_backend_repository_url>:latest -f backend/Dockerfile .
docker push <ecr_backend_repository_url>:latest

# Frontend
docker build -t <ecr_frontend_repository_url>:latest ./frontend
docker push <ecr_frontend_repository_url>:latest

# One-off DB migration (creates the schema + `CREATE EXTENSION vector`):
terraform output -raw migrate_run_task_command | bash

# Roll the services onto the freshly pushed images:
for svc in backend frontend worker; do
  aws ecs update-service --cluster $(terraform output -raw ecs_cluster_name) \
    --service $svc --force-new-deployment --region <region>
done
```

Open `http://<alb_dns_name>` — the chat UI. Upload docs to the `docs_bucket` and
the worker indexes them (S3 → SQS → worker); they become queryable within seconds.

## Enabling Google SSO

Set `auth_enabled = true` (+ `google_oauth_client_id`, `google_hosted_domain`, and
the `TF_VAR_auth_secret` / `TF_VAR_google_client_secret` envs), `apply`, then add
**`<app_url>/api/auth/callback`** as an authorized redirect URI on the OAuth client
in Google Cloud Console (`app_url` is a Terraform output). For a real domain, set
`acm_certificate_arn` to an ACM cert so the app is served over HTTPS.

## Teardown

```bash
terraform destroy
```

Everything is set to delete cleanly (`force_delete`/`force_destroy`,
`skip_final_snapshot`); empty the docs bucket first if versioned objects remain.

## Not included (follow-ups)

CI/CD (build→ECR→deploy on push), Route 53 records, autoscaling policies, WAF, and
CloudFront. The cert-ARN variable is wired, but DNS/cert issuance is manual.
