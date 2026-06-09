terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }

  # For real use, switch to an encrypted remote backend so state (which holds
  # the secret values below) is not kept on a laptop:
  #
  # backend "s3" {
  #   bucket       = "my-tf-state"
  #   key          = "rag/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}
