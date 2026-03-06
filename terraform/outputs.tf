# EKS Cluster Outputs
output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.eks.name
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = aws_eks_cluster.eks.endpoint
}

output "cluster_certificate_authority_data" {
  description = "EKS cluster certificate authority data"
  value       = aws_eks_cluster.eks.certificate_authority[0].data
  sensitive   = true
}

# Database Outputs
output "postgres_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "postgres_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.postgres.port
}

output "db_secret_arn" {
  description = "Database secret ARN"
  value       = data.aws_secretsmanager_secret.existing_db_secret.arn
  sensitive   = true
}

# Redis Outputs
output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "redis_port" {
  description = "ElastiCache Redis port"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].port
}

# Load Balancer Outputs
output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = aws_lb.alb.dns_name
}

output "alb_zone_id" {
  description = "Application Load Balancer zone ID"
  value       = aws_lb.alb.zone_id
}

# IAM Outputs
output "eks_role_arn" {
  description = "EKS cluster role ARN"
  value       = aws_iam_role.eks_role.arn
}

# VPC Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = [aws_subnet.private_1.id, aws_subnet.private_2.id]
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = [aws_subnet.public_1.id, aws_subnet.public_2.id]
}

# Security Group Outputs
output "eks_nodes_security_group_id" {
  description = "EKS nodes security group ID"
  value       = aws_security_group.eks_nodes.id
}

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = aws_security_group.alb.id
}

# API URL (for easy access)
output "api_url" {
  description = "Main API URL (use this for testing)"
  value       = "http://${aws_lb.alb.dns_name}"
}

output "db_host" {
  description = "Database host endpoint"
  value       = aws_db_instance.postgres.address
}

output "redis_host" {
  description = "Redis host endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "alb_dns" {
  description = "Application Load Balancer DNS name"
  value       = aws_lb.alb.dns_name
}

output "alb_controller_policy_arn" {
  description = "AWS Load Balancer Controller IAM policy ARN"
  value       = aws_iam_policy.alb_controller.arn
}

output "alb_controller_role_arn" {
  description = "AWS Load Balancer Controller IAM role ARN"
  value       = aws_iam_role.alb_controller.arn
}

output "eks_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.eks.name
}