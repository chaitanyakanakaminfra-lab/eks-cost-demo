# Cost Attribution — read-only AWS permissions
resource "aws_iam_policy" "cost_attribution" {
  name        = "${var.cluster_name}-cost-attribution"
  description = "Read-only access for EKS Cost Attribution tool"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatch"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
          "cloudwatch:GetMetricData",
        ]
        Resource = "*"
      },
      {
        Sid    = "Pricing"
        Effect = "Allow"
        Action = [
          "pricing:GetProducts",
          "pricing:DescribeServices",
        ]
        Resource = "*"
      },
      {
        Sid    = "CostExplorer"
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetDimensionValues",
        ]
        Resource = "*"
      },
      {
        Sid    = "EKS"
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters",
        ]
        Resource = "*"
      },
    ]
  })
}

# Atlantis — Terraform plan/apply permissions
resource "aws_iam_policy" "atlantis" {
  name        = "${var.cluster_name}-atlantis"
  description = "Permissions for Atlantis to run terraform plan and apply"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TerraformOperations"
        Effect = "Allow"
        Action = [
          "ec2:*", "eks:*", "iam:*",
          "s3:*", "dynamodb:*",
          "cloudwatch:*", "logs:*",
          "elasticloadbalancing:*",
          "autoscaling:*", "kms:*",
        ]
        Resource = "*"
      }
    ]
  })
}

# IRSA — Cost Attribution service account
module "cost_attribution_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.cluster_name}-cost-attribution"

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["default:cost-attribution"]
    }
  }

  role_policy_arns = {
    cost_attribution = aws_iam_policy.cost_attribution.arn
  }
}

# IRSA — Atlantis service account
module "atlantis_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.cluster_name}-atlantis"

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["atlantis:atlantis"]
    }
  }

  role_policy_arns = {
    atlantis = aws_iam_policy.atlantis.arn
  }
}
