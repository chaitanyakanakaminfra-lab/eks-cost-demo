#!/usr/bin/env bash
# teardown.sh — Delete everything and stop all AWS charges
set -euo pipefail

[ -f ".env" ] && export $(grep -v '^#' .env | xargs) || true

AWS_REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${CLUSTER_NAME:-eks-cost-demo}"

RED='\033[0;31m'; GREEN='\033[0;32m'
BOLD='\033[1m'; RESET='\033[0m'

echo -e "${RED}${BOLD}"
echo "════════════════════════════════════════"
echo "  WARNING: Deletes ALL AWS resources"
echo "════════════════════════════════════════"
echo -e "${RESET}"

read -p "Type 'delete' to confirm: " CONFIRM
[ "$CONFIRM" = "delete" ] || { echo "Aborted."; exit 0; }

echo "[1/4] Removing ArgoCD applications..."
kubectl delete application --all -n argocd \
  --ignore-not-found 2>/dev/null || true
sleep 30

echo "[2/4] Running terraform destroy..."
cd terraform
terraform destroy -auto-approve \
  -var="aws_region=${AWS_REGION}" \
  -var="cluster_name=${CLUSTER_NAME}"
cd ..

echo "[3/4] Deleting S3 state bucket..."
ACCOUNT_ID=$(aws sts get-caller-identity \
  --query Account --output text)
STATE_BUCKET="${CLUSTER_NAME}-tfstate-${ACCOUNT_ID}"
aws s3 rm "s3://$STATE_BUCKET" --recursive 2>/dev/null || true
aws s3api delete-bucket \
  --bucket "$STATE_BUCKET" \
  --region "$AWS_REGION" 2>/dev/null || true

echo "[4/4] Deleting DynamoDB lock table..."
aws dynamodb delete-table \
  --table-name "${CLUSTER_NAME}-tflock" \
  --region "$AWS_REGION" 2>/dev/null || true

echo -e "${GREEN}${BOLD}All deleted. AWS charges stopped.${RESET}"
