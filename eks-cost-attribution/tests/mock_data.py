"""
Mock data — test the tool locally without any AWS account.
Run: cd eks-cost-attribution && python -m tests.mock_data
"""
from cost_attribution.analyzer import CostAnalyzer
from cost_attribution.reporter import Reporter

MOCK_NODES = [
    {"name": "node-1", "instance_type": "t3.small",
     "allocatable_cpu": 1900, "allocatable_memory": 1800},
    {"name": "node-2", "instance_type": "t3.small",
     "allocatable_cpu": 1900, "allocatable_memory": 1800},
]

MOCK_NODE_COSTS = {
    "node-1": 15.18,  # t3.small $0.0208/hr * 730
    "node-2": 15.18,
}

MOCK_PODS = [
    {"name": "payment-api-abc", "namespace": "payments",
     "deployment": "payment-api", "node": "node-1",
     "phase": "Running", "cpu_request": 300, "memory_request": 256},

    {"name": "auth-svc-def", "namespace": "auth",
     "deployment": "auth-service", "node": "node-1",
     "phase": "Running", "cpu_request": 100, "memory_request": 128},

    {"name": "search-ghi", "namespace": "search",
     "deployment": "search-api", "node": "node-2",
     "phase": "Running", "cpu_request": 2000, "memory_request": 4096},

    {"name": "ml-old-jkl", "namespace": "staging",
     "deployment": "ml-pipeline", "node": "node-2",
     "phase": "Running", "cpu_request": 1000, "memory_request": 2048},
]

# Actual usage — ml-pipeline uses almost nothing (idle)
MOCK_USAGE = {
    "payment-api-abc": {"cpu_actual_millicores": 180, "memory_actual_mib": 190},
    "auth-svc-def":    {"cpu_actual_millicores":  80, "memory_actual_mib":  90},
    "search-ghi":      {"cpu_actual_millicores": 120, "memory_actual_mib": 400},
    "ml-old-jkl":      {"cpu_actual_millicores":   1, "memory_actual_mib":   5},
}

if __name__ == "__main__":
    analyzer = CostAnalyzer(
        nodes=MOCK_NODES,
        pods=MOCK_PODS,
        node_costs=MOCK_NODE_COSTS,
        usage_data=MOCK_USAGE,
    )
    report = analyzer.generate_report()
    Reporter(report).print_table()
