.PHONY: help bootstrap teardown cost-report argocd-ui argocd-apps atlantis-url clean

CLUSTER ?= eks-cost-demo
REGION  ?= us-east-1

help:
	@echo ""
	@echo "  EKS Cost Demo — Commands"
	@echo ""
	@echo "  SETUP"
	@echo "    make bootstrap       Bring up entire stack"
	@echo "    make teardown        Delete everything"
	@echo ""
	@echo "  DAILY USE"
	@echo "    make cost-report     Run cost attribution"
	@echo "    make argocd-ui       Open ArgoCD UI"
	@echo "    make argocd-apps     Show all ArgoCD apps"
	@echo "    make atlantis-url    Print Atlantis webhook URL"
	@echo "    make clean           Remove cache files"
	@echo ""

bootstrap:
	./scripts/bootstrap.sh

teardown:
	./scripts/teardown.sh

cost-report:
	cd eks-cost-attribution && python main.py \
		--cluster $(CLUSTER) \
		--region  $(REGION) \
		--format  table

cost-report-mock:
	cd eks-cost-attribution && python -m tests.mock_data

argocd-ui:
	@echo "ArgoCD → https://localhost:8080   user: admin"
	@printf "Password: "; kubectl -n argocd get secret argocd-initial-admin-secret \
		-o jsonpath="{.data.password}" | base64 -d; echo
	kubectl port-forward svc/argocd-server -n argocd 8080:443

argocd-apps:
	kubectl get applications -n argocd -o wide

atlantis-url:
	@printf "Atlantis webhook URL:\n  http://"
	@kubectl get svc atlantis -n atlantis \
		-o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
	@printf "/events\n"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
