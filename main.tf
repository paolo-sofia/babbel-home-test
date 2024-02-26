terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  region                      = "eu-central-1"
  redis_host                  = "redis-host"
  redis_port                  = 6379
  redis_db                    = 0
  function_name               = "lambda_function"
  function_handler            = "lambda_function.lambda_handler"
  function_runtime            = "python3.11"
  function_timeout_in_seconds = 5
  function_source_dir         = "${path.module}/src/babbel_home_assignement/${local.function_name}"
}

provider "aws" {
  region = local.region
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_policy" "s3_policy" {
  name        = "default_policy_name"
  description = "S3 Access"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:*",
        ]
        Effect   = "Allow"
        Resource = "*"
      },
    ]
  })
}


resource "aws_iam_role" "iam_for_lambda" {
  name               = "iam_for_lambda"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  managed_policy_arns = [aws_iam_policy.s3_policy.arn]
}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = local.function_source_dir
  output_path = "${local.function_source_dir}.zip"
}

resource "aws_lambda_function" "lambda_function" {
  filename         = "${local.function_source_dir}.zip"
  function_name    = local.function_name
  handler          = local.function_handler
  runtime          = local.function_runtime
  timeout          = local.function_timeout_in_seconds
  source_code_hash = data.archive_file.data_preprocessor.output_base64sha256

  role = aws_iam_role.iam_for_lambda.arn

  environment {
    variables = {
      REDIS_HOST = local.redis_host,
      REDIS_PORT = local.redis_port,
      REDIS_DB   = local.redis_db,
    }
  }
}

data "archive_file" "data_preprocessor" {
  source_dir  = local.function_source_dir
  type        = "zip"
  output_path = "${local.function_source_dir}.zip"
}

resource "aws_iam_role" "lambda_role" {
  name = "terraform_aws_lambda_role"

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
  port                    = local.redis_port
}