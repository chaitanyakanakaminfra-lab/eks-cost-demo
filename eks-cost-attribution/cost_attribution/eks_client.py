"""
EKSClient — connects to EKS using boto3 + kubernetes Python client.
Fetches nodes with instance types and pods with resource requests.
"""
import boto3
import base64
import tempfile
from kubernetes import client
from kubernetes.client.rest import ApiException


class EKSClient:
    def __init__(self, cluster_name: str, region: str):
        self.cluster_name = cluster_name
        self.region       = region
        self._configure_client()
        self.v1 = client.CoreV1Api()

    def _configure_client(self):
        """Authenticate to EKS using boto3 — no kubeconfig needed."""
        eks     = boto3.client("eks", region_name=self.region)
        cluster = eks.describe_cluster(name=self.cluster_name)["cluster"]

        ca_bytes = base64.b64decode(
            cluster["certificateAuthority"]["data"]
        )
        ca_file  = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
        ca_file.write(ca_bytes)
        ca_file.close()

        token = self._get_token()

        cfg             = client.Configuration()
        cfg.host        = cluster["endpoint"]
        cfg.ssl_ca_cert = ca_file.name
        cfg.api_key     = {"authorization": f"Bearer {token}"}
        client.Configuration.set_default(cfg)

    def _get_token(self) -> str:
        """Generate short-lived EKS bearer token using STS."""
        sts = boto3.client("sts", region_name=self.region)
        url = sts.generate_presigned_url(
            "get_caller_identity",
            Params={},
            ExpiresIn=60,
            HttpMethod="GET",
        )
        token = "k8s-aws-v1." + base64.urlsafe_b64encode(
            url.encode("utf-8")
        ).rstrip(b"=").decode("utf-8")
        return token

    def get_nodes(self) -> list[dict]:
        """Return nodes with instance type and allocatable resources."""
        nodes = []
        for n in self.v1.list_node().items:
            labels = n.metadata.labels or {}
            alloc  = n.status.allocatable or {}
            nodes.append({
                "name": n.metadata.name,
                "instance_type": labels.get(
                    "node.kubernetes.io/instance-type", "unknown"
                ),
                "allocatable_cpu":    self._parse_cpu(
                    alloc.get("cpu", "0")
                ),
                "allocatable_memory": self._parse_mem(
                    alloc.get("memory", "0Ki")
                ),
            })
        return nodes

    def get_pods(self, namespace: str = "all") -> list[dict]:
        """Return pods with resource requests and owner deployment."""
        SKIP = {"kube-system", "kube-public", "kube-node-lease"}
        pods = []

        raw = (
            self.v1.list_pod_for_all_namespaces()
            if namespace == "all"
            else self.v1.list_namespaced_pod(namespace=namespace)
        )

        for pod in raw.items:
            if pod.metadata.namespace in SKIP:
                continue
            cpu_req = mem_req = 0
            for c in pod.spec.containers:
                if c.resources and c.resources.requests:
                    cpu_req += self._parse_cpu(
                        c.resources.requests.get("cpu", "0")
                    )
                    mem_req += self._parse_mem(
                        c.resources.requests.get("memory", "0Ki")
                    )
            pods.append({
                "name":           pod.metadata.name,
                "namespace":      pod.metadata.namespace,
                "deployment":     self._deployment(pod),
                "node":           pod.spec.node_name,
                "phase":          pod.status.phase,
                "cpu_request":    cpu_req,
                "memory_request": mem_req,
            })
        return pods

    @staticmethod
    def _deployment(pod) -> str:
        for ref in (pod.metadata.owner_references or []):
            if ref.kind == "ReplicaSet":
                parts = ref.name.rsplit("-", 2)
                return parts[0] if len(parts) >= 2 else ref.name
        return pod.metadata.name

    @staticmethod
    def _parse_cpu(s: str) -> float:
        return float(s[:-1]) if s.endswith("m") else float(s) * 1000

    @staticmethod
    def _parse_mem(s: str) -> float:
        for suffix, factor in [
            ("Ki", 1/1024), ("Mi", 1), ("Gi", 1024), ("Ti", 1024**2)
        ]:
            if s.endswith(suffix):
                return float(s[:-len(suffix)]) * factor
        return float(s) / (1024 ** 2)
