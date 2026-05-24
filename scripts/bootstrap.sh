#!/usr/bin/env bash
# bootstrap.sh — Bring up complete EKS demo stack with one command
set -euo pipefail

# ── Load .env ─────────────────────────────────────────────────────────────────
[ -f ".env" ] || { echo "ERROR: .env not found. Copy .env.example to .env"; exit 1; }
export $(grep -v '^#' .env | xargs)

# ── Validate required vars ────────────────────────────────────────────────────
for var in AWS_REGION CLUSTER_NAME GITHUB_USER GITHUB_REPO GITHUB_TOKEN ATLANTIS_WEBHOOK_SECRET; do
  [ -n "${!var:-}" ] || { echo "ERROR: $var not set in .env"; exit 1; }
done

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
TOTAL=10

step() { echo -e "\n${CYAN}${BOLD}[$1/$TOTAL]${RESET} $2"; }
ok()   { echo -e "${GREEN}  ✅ $1${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${RESET}"; }

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
STATE_BUCKET="${CLUSTER_NAME}-tfstate-${ACCOUNT_ID}"
LOCK_TABLE="${CLUSTER_NAME}-tflock"

echo -e "\n${BOLD}EKS Cost Demo — Full Stack Bootstrap${RESET}"
echo "  Cluster:  $CLUSTER_NAME  |  Region: $AWS_REGION"
echo "  GitHub:   $GITHUB_USER/$GITHUB_REPO"
echo "  Estimate: ~$5-7 total for 48h"
echo ""

# ── Step 1: S3 + DynamoDB ─────────────────────────────────────────────────────
step 1 "Creating Terraform state backend..."

aws s3api create-bucket \
  --bucket "$STATE_BUCKET" \
  --region "$AWS_REGION" \
  $([ "$AWS_REGION" != "us-east-1" ] && \
    echo "--create-bucket-configuration LocationConstraint=$AWS_REGION") \
  2>/dev/null && ok "Created S3 bucket: $STATE_BUCKET" || ok "Bucket exists"

aws s3api put-bucket-versioning \
  --bucket "$STATE_BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "$STATE_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws dynamodb create-table \
  --table-name "$LOCK_TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$AWS_REGION" \
  2>/dev/null && ok "Created DynamoDB: $LOCK_TABLE" || ok "Table exists"

# ── Step 2: Write backend config ──────────────────────────────────────────────
step 2 "Writing Terraform backend config..."

cat > terraform/backend.tf << TFEOF
terraform {
  backend "s3" {
    bucket         = "$STATE_BUCKET"
    key            = "eks/terraform.tfstate"
    region         = "$AWS_REGION"
    dynamodb_table = "$LOCK_TABLE"
    encrypt        = true
  }
}
TFEOF
ok "terraform/backend.tf written"

# ── Step 3: Terraform init ────────────────────────────────────────────────────
step 3 "Running terraform init..."
cd terraform
terraform init -upgrade
ok "Terraform initialised"

# ── Step 4: Terraform apply ───────────────────────────────────────────────────
step 4 "Running terraform apply — VPC + EKS + IAM (15-20 min)..."
warn "Slow step — grab a coffee."

terraform apply -auto-approve \
  -var="aws_region=${AWS_REGION}" \
  -var="cluster_name=${CLUSTER_NAME}"

ATLANTIS_ROLE_ARN=$(terraform output -raw atlantis_iam_role_arn)
ok "Terraform apply complete"
cd ..

# ── Step 5: Configure kubectl ─────────────────────────────────────────────────
step 5 "Configuring kubectl..."
aws eks update-kubeconfig \
  --region "$AWS_REGION" \
  --name   "$CLUSTER_NAME"
kubectl get nodes
ok "kubectl configured"

# ── Step 6: Patch Atlantis IAM role ARN ──────────────────────────────────────
step 6 "Injecting Atlantis IAM role ARN..."
sed -i "s|ATLANTIS_ROLE_ARN|${ATLANTIS_ROLE_ARN}|g" \
  atlantis-values/values.yaml
ok "Role ARN patched: $ATLANTIS_ROLE_ARN"

# ── Step 7: Commit updated values ────────────────────────────────────────────
step 7 "Pushing updated atlantis values to GitHub..."
git add atlantis-values/values.yaml
git commit -m "chore: inject atlantis IAM role ARN" || true
git push
ok "Pushed to GitHub"

# ── Step 8: Create Kubernetes secrets ─────────────────────────────────────────
step 8 "Creating Kubernetes secrets for Atlantis..."
kubectl create namespace atlantis \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic atlantis-github-secrets \
  --from-literal=github-token="${GITHUB_TOKEN}" \
  --from-literal=webhook-secret="${ATLANTIS_WEBHOOK_SECRET}" \
  -n atlantis \
  --dry-run=client -o yaml | kubectl apply -f -
ok "Kubernetes secrets created"

# ── Step 9: Deploy App of Apps ────────────────────────────────────────────────
step 9 "Deploying ArgoCD App of Apps..."
kubectl wait \
  --for=condition=available \
  deployment/argocd-server \
  -n argocd \
  --timeout=300s

kubectl apply -f argocd/app-of-apps.yaml
ok "App of Apps deployed — ArgoCD syncing all apps"
echo "  Waiting 60s for apps to start..."
sleep 60

# ── Step 10: Print access details ─────────────────────────────────────────────
step 10 "Gathering access details..."

ARGOCD_PASS=$(kubectl -n argocd get secret \
  argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d 2>/dev/null)

GRAFANA_LB=$(kubectl get svc \
  prometheus-stack-grafana -n monitoring \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' \
  2>/dev/null || echo "pending")

ATLANTIS_LB=$(kubectl get svc atlantis -n atlantis \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' \
  2>/dev/null || echo "pending")

echo -e "\n${GREEN}${BOLD}"
echo "════════════════════════════════════════════════════"
echo "  SETUP COMPLETE"
echo "════════════════════════════════════════════════════"
echo ""
echo "  ARGOCD"
echo "    make argocd-ui"
echo "    Username: admin"
echo "    Password: $ARGOCD_PASS"
echo ""
echo "  GRAFANA"
echo "    URL:      http://$GRAFANA_LB"
echo "    Username: admin"
echo "    Password: demo-grafana-2024"
echo ""
echo "  ATLANTIS WEBHOOK"
echo "    URL: http://$ATLANTIS_LB/events"
echo "    Add to: GitHub repo → Settings → Webhooks"
echo ""
echo "  COST ATTRIBUTION"
echo "    make cost-report"
echo ""
echo "  DELETE EVERYTHING"
echo "    ./scripts/teardown.sh"
echo ""
echo "════════════════════════════════════════════════════"
echo -e "${RESET}"
