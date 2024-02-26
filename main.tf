terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

variable "env_name" {
  description = "Environment name"
}

variable "region" {
  type = string
  default = "eu-central-1"
}

variable "redis_host" {
  type = string
  default = "redis-host"
}

variable "redis_port" {
  type = number
  default = 6379
}

provider "aws" {
  region = var.region
}

locals {
  function_name               = "text_scrambler"
  function_handler            = "lambda_function.handler"
  function_runtime            = "python3.11"
  function_timeout_in_seconds = 5

  function_source_dir = "${path.module}/babbel_home_assignement/${local.function_name}"
}

resource "aws_lambda_function" "lambda_function" {
  function_name = local.function_name
  handler       = local.function_handler
  runtime       = local.function_runtime
  timeout       = local.function_timeout_in_seconds

  filename         = "${local.function_source_dir}.zip"
  source_code_hash = data.archive_file.data_preprocessor.output_base64sha256

  role = aws_iam_role.function_role.arn

  environment {
    variables = {
      ENVIRONMENT = var.env_name
    }
  }
}

data "archive_file" "data_preprocessor" {
  source_dir  = local.function_source_dir
  type        = "zip"
  output_path = "${local.function_source_dir}.zip"
}

resource "aws_iam_role" "function_role" {
  name = "${local.function_name}-${var.env_name}"

  assume_role_policy = jsonencode({
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      },
    ]
  })
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id              = "redis-cluster"
  engine                  = "redis"
  node_type               = "cache.t2.micro"
  num_cache_nodes         = 1
  parameter_group_name    = "default.redis7.2"
  engine_version          = "7.2"
  port                    = var.redis_port
}