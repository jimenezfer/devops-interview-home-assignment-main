#!/bin/bash

# Setup Database Secrets from AWS Secrets Manager
set -e

echo "🔐 Setting up Database Secrets from AWS Secrets Manager"

# Configuration
SECRET_NAME="myDbPassword"
NAMESPACE="default"
SECRET_NAME_K8S="ai-assistant-db-secret"

# Get database credentials from AWS Secrets Manager
echo "📥 Retrieving database credentials from AWS Secrets Manager..."
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id $SECRET_NAME --query SecretString --output text)

# Extract username and password
DB_USERNAME=$(echo $SECRET_JSON | jq -r .username)
DB_PASSWORD=$(echo $SECRET_JSON | jq -r .password)

echo "👤 Username: $DB_USERNAME"
echo "🔑 Password: [REDACTED]"

# Create Kubernetes secret
echo "🚀 Creating Kubernetes secret..."
kubectl create secret generic $SECRET_NAME_K8S \
  --from-literal=username=$DB_USERNAME \
  --from-literal=password=$DB_PASSWORD \
  --namespace=$NAMESPACE \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Database secret created successfully!"
echo "📋 Secret name: $SECRET_NAME_K8S"
echo "🔍 Verify with: kubectl get secret $SECRET_NAME_K8S -o yaml"
