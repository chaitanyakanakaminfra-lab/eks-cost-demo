output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_region" {
  value = var.aws_region
}

output "configure_kubectl" {
  description = "Run this to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

output "atlantis_iam_role_arn" {
  description = "IAM role ARN for Atlantis"
  value       = module.atlantis_irsa.iam_role_arn
}

output "cost_attribution_iam_role_arn" {
  description = "IAM role ARN for cost attribution tool"
  value       = module.cost_attribution_irsa.iam_role_arn
}
