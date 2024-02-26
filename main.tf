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
  function_source_dir         = "${path.module}/src/babbel_home_assignement/"
  venv_source_dir             = "${path.module}/.venv/lib/python3.11/site-packages/"
  s3_bucket_name              = "data-pipeline-bucket"
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

data "aws_iam_policy_document" "s3_role" {
  statement {
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:AbortMultipartUpload",
      "s3:ListBucket",
      "s3:DeleteObject",
      "s3:GetObjectVersion",
      "s3:ListMultipartUploadParts"
    ]

    resources = [
      "arn:aws:s3:::${s3_bucket_name}/*",
      "arn:aws:s3:::${s3_bucket_name}",
    ]
  }
}


resource "aws_iam_policy" "s3_policy" {
  name        = "default_policy_name"
  description = "S3 Access"
  policy      = data.aws_iam_policy_document.s3_role.json
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

  source {
    content  = file("${local.function_source_dir}${local.function_name}.py")
    filename = "${local.function_name}.py"
  }

  source {
    content  = file(local.venv_source_dir)
    filename = "site-packages/"
  }
}

resource "aws_lambda_function" "lambda_function" {
  filename         = "${local.function_source_dir}.zip"
  function_name    = local.function_name
  handler          = local.function_handler
  runtime          = local.function_runtime
  timeout          = local.function_timeout_in_seconds
  source_code_hash = data.archive_file.lambda.output_base64sha256

  role = aws_iam_role.iam_for_lambda.arn

  environment {
    variables = {
      REDIS_HOST = aws_elasticache_cluster.redis.cache_nodes.0.address,
      REDIS_PORT = local.redis_port,
      REDIS_DB   = local.redis_db,
      S3_BUCKET  = local.s3_bucket_name
    }
  }
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