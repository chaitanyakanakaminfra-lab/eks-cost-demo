"""
CostAnalyzer — core attribution logic.
Calculates pod cost as fraction of node cost based on resource requests.
Identifies waste and idle workloads.
"""
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class PodCost:
    name:           str
    namespace:      str
    deployment:     str
    monthly_cost:   float
    cpu_request:    float
    cpu_actual:     float
    memory_request: float
    memory_actual:  float
    waste_pct:      float
    is_idle:        bool
    status:         str


@dataclass
class NamespaceReport:
    name:         str
    monthly_cost: float
    waste_pct:    float
    pods:         list = field(default_factory=list)


@dataclass
class ClusterReport:
    cluster_name:       str
    total_monthly_cost: float
    total_waste_pct:    float
    potential_savings:  float
    namespaces:         list = field(default_factory=list)
    idle_workloads:     list = field(default_factory=list)


class CostAnalyzer:
    def __init__(
        self,
        nodes,
        pods,
        node_costs,
        usage_data,
        idle_days=14,
        waste_threshold=50.0,
    ):
        self.nodes           = {n["name"]: n for n in nodes}
        self.pods            = pods
        self.node_costs      = node_costs
        self.usage_data      = usage_data
        self.waste_threshold = waste_threshold

    def generate_report(self) -> ClusterReport:
        pod_costs = [self._pod_cost(pod) for pod in self.pods]

        ns_groups: dict = defaultdict(list)
        for pc in pod_costs:
            ns_groups[pc.namespace].append(pc)

        namespaces = []
        for ns, ns_pods in ns_groups.items():
            total = sum(p.monthly_cost for p in ns_pods)
            w_avg = (
                sum(p.monthly_cost * p.waste_pct for p in ns_pods) / total
                if total > 0 else 0
            )
            namespaces.append(NamespaceReport(
                name=ns,
                monthly_cost=total,
                waste_pct=w_avg,
                pods=ns_pods,
            ))

        namespaces.sort(key=lambda x: x.monthly_cost, reverse=True)

        total_cost  = sum(p.monthly_cost for p in pod_costs)
        total_waste = (
            sum(p.monthly_cost * p.waste_pct for p in pod_costs) / total_cost
            if total_cost > 0 else 0
        )
        savings = sum(
            p.monthly_cost * p.waste_pct / 100 for p in pod_costs
        )

        return ClusterReport(
            cluster_name=list(self.nodes.keys())[0] if self.nodes else "cluster",
            total_monthly_cost=total_cost,
            total_waste_pct=total_waste,
            potential_savings=savings,
            namespaces=namespaces,
            idle_workloads=[p for p in pod_costs if p.is_idle],
        )

    def _pod_cost(self, pod: dict) -> PodCost:
        node      = self.nodes.get(pod.get("node"), {})
        node_cost = self.node_costs.get(pod.get("node"), 0.0)
        alloc_cpu = node.get("allocatable_cpu", 1000)
        alloc_mem = node.get("allocatable_memory", 1024)
        cpu_req   = pod.get("cpu_request", 0)
        mem_req   = pod.get("memory_request", 0)

        cpu_frac     = cpu_req / alloc_cpu if alloc_cpu > 0 else 0
        mem_frac     = mem_req / alloc_mem if alloc_mem > 0 else 0
        monthly_cost = ((cpu_frac + mem_frac) / 2) * node_cost

        usage      = self.usage_data.get(pod["name"], {})
        cpu_actual = usage.get("cpu_actual_millicores", 0)
        mem_actual = usage.get("memory_actual_mib", 0)

        waste_pct = (
            max(0, (cpu_req - cpu_actual) / cpu_req * 100)
            if cpu_req > 0 else 0
        )
        is_idle = cpu_actual < cpu_req * 0.01 and cpu_req > 0
        status  = (
            "idle" if is_idle
            else "overprovisioned" if waste_pct >= self.waste_threshold
            else "healthy"
        )

        return PodCost(
            name=pod["name"],
            namespace=pod["namespace"],
            deployment=pod["deployment"],
            monthly_cost=monthly_cost,
            cpu_request=cpu_req,
            cpu_actual=cpu_actual,
            memory_request=mem_req,
            memory_actual=mem_actual,
            waste_pct=waste_pct,
            is_idle=is_idle,
            status=status,
        )
