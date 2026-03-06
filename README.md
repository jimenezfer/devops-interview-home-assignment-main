# AI Assistant — EKS + vLLM + FastAPI

AI-powered question answering API deployed on AWS EKS with SmolLM2-135M-Instruct served via vLLM, backed by Aurora PostgreSQL and ElastiCache Redis.

---

## Architecture
```
                          ┌─────────────────────────────────────────────────────┐
                          │                    AWS Cloud                         │
                          │                                                       │
          Internet        │   ┌──────────┐      ┌─────────────────────────────┐ │
        ─────────────────►│   │   ALB    │─────►│         EKS Cluster         │ │
        HTTP :80          │   │(public)  │      │                             │ │
                          │   └──────────┘      │  ┌─────────┐  ┌─────────┐  │ │
                          │                     │  │FastAPI  │  │  vLLM   │  │ │
                          │                     │  │  API    │─►│SmolLM2  │  │ │
                          │                     │  │(x2 pods)│  │(x1 pod) │  │ │
                          │                     │  └────┬────┘  └─────────┘  │ │
                          │                     │       │                     │ │
                          │                     └───────┼─────────────────────┘ │
                          │                             │                        │
                          │              ┌──────────────┼──────────────┐        │
                          │              │              │               │        │
                          │      ┌───────▼──────┐ ┌────▼─────┐        │        │
                          │      │    Aurora     │ │ElastiCache│        │        │
                          │      │  PostgreSQL   │ │  Redis    │        │        │
                          │      │  (private)    │ │(private)  │        │        │
                          │      └──────────────┘ └──────────┘        │        │
                          │                                             │        │
                          │         ┌───────────────────────┐          │        │
                          │         │    AWS Secrets Manager │          │        │
                          │         │      (myDbPassword)    │          │        │
                          │         └───────────────────────┘          │        │
                          └─────────────────────────────────────────────────────┘
```

### Component Overview

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Compute | EKS (t3.small) | Container orchestration |
| API | FastAPI (Python) | REST endpoints + chatbox UI |
| LLM | vLLM + SmolLM2-135M | AI inference engine |
| Database | Aurora PostgreSQL 16 | Question history + cache metadata |
| Cache | ElastiCache Redis | Response caching (1hr TTL) |
| Load Balancer | AWS ALB | Internet-facing ingress |
| Secrets | AWS Secrets Manager | DB credentials |
| IaC | Terraform | Infrastructure provisioning |
| Deployment | Helm | Kubernetes package management |

### Request Flow
```
User → ALB → FastAPI Pod
                │
                ├── Check Redis cache
                │     └── HIT  → return cached answer
                │
                └── MISS → vLLM (SmolLM2-135M-Instruct)
                              └── Store in Redis + Aurora
                              └── Return answer to user
```

---

## Project Structure
```
devops-interview-home-assignment/
├── terraform/                  # AWS infrastructure
│   ├── main.tf                 # VPC, EKS, RDS, Redis, ALB, IAM
│   ├── variables.tf            # Input variables
│   └── outputs.tf              # Terraform outputs
├── k8s/                        # Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── deployment.yaml         # FastAPI deployment
│       ├── vllm-deployment.yaml    # vLLM deployment
│       ├── service.yaml            # FastAPI service
│       ├── vllm-service.yaml       # vLLM service
│       ├── ingress.yaml            # ALB ingress
│       ├── secret.yaml             # DB secret placeholder
│       ├── serviceaccount.yaml     # Kubernetes service account
│       └── db-init-job.yaml        # Schema migration job
├── code/                       # Application code
│   ├── main.py                 # FastAPI app + chatbox UI
│   ├── Dockerfile
│   └── requirements.txt
├── setup-secrets.sh            # DB secret bootstrap
└── README.md
```

---

## Quick Start

### Prerequisites
- AWS CLI configured
- Docker installed
- kubectl installed
- Helm installed
- Terraform installed

### Deployment

```bash
# ============================================================
# DEPLOYMENT STEPS
# ============================================================

# STEP 1 - TERRAFORM
cd terraform
terraform init
terraform apply

# STEP 2 - CONFIGURE KUBECTL
aws eks update-kubeconfig \
  --region us-west-1 \
  --name $(terraform output -raw eks_name)

kubectl wait --for=condition=Ready nodes --all --timeout=300s

# STEP 3 - ALB CONTROLLER
helm repo add eks https://aws.github.io/eks-charts
helm repo update

helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=$(terraform output -raw eks_name) \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=$(terraform output -raw alb_controller_role_arn)

# STEP 4 - BUILD AND PUSH DOCKER IMAGE
cd ../code
docker build -t foxelvoret/ai-assistant:latest .
docker push foxelvoret/ai-assistant:latest

# STEP 5 - CREATE DATABASE SECRET
cd ..
chmod +x setup-secrets.sh
./setup-secrets.sh

# STEP 6 - ADOPT SECRET INTO HELM
kubectl annotate secret ai-assistant-db-secret meta.helm.sh/release-name=ai-assistant --overwrite
kubectl annotate secret ai-assistant-db-secret meta.helm.sh/release-namespace=default --overwrite
kubectl label secret ai-assistant-db-secret app.kubernetes.io/managed-by=Helm --overwrite

# STEP 7 - DEPLOY WITH HELM
cd terraform

DB_HOST=$(terraform output -raw db_host)
REDIS_HOST=$(terraform output -raw redis_host)
ALB_DNS=$(terraform output -raw alb_dns)

helm upgrade --install ai-assistant ../k8s \
  --set database.host=$DB_HOST \
  --set database.port=5432 \
  --set redis.host=$REDIS_HOST \
  --set ingress.host=$ALB_DNS \
  --wait=false

# STEP 8 - VERIFY
curl http://$ALB_DNS/health

curl -X POST http://$ALB_DNS/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is 2+2?"}'

echo "Chatbox: http://$ALB_DNS/chatbox"
```

---

## Scaling & Performance Optimizations

### Horizontal Pod Autoscaling (HPA)
```bash
# Enable HPA for API pods (stateless, scales independently)
kubectl autoscale deployment ai-assistant-api \
  --cpu-percent=70 \
  --min=2 \
  --max=10

# Monitor HPA
kubectl get hpa
kubectl describe hpa ai-assistant-api
```

### Additional Performance Optimizations

- **GPU Acceleration**: Upgrade node instance type from t3.medium to g4dn.xlarge for GPU-based inference — reduces vLLM response time from 10-15s to under 1s
- **Model Cache Persistence**: Add a PersistentVolumeClaim for the HuggingFace model cache directory — eliminates the 5-10 min cold start every time the vLLM pod restarts
- **Redis Cache Optimization**: Increase Redis cache TTL for stable knowledge domains — cache hits bypass vLLM entirely which is the most cost-effective scaling strategy
---

## License

MIT License - feel free to use this as a reference for your own AI infrastructure projects.
