variable "aws_region" {
  default = "us-west-1"
}

variable "cluster_name" {
  default = "devops-cluster"
}

variable "project_name" {
  description = "devops"
  type        = string
}

variable "db_username" {
  description = "The database username."
  type        = string
}

variable "db_password" {
  description = "The database password."
  type        = string
}