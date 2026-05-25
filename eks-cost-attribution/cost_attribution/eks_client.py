"""
EKSClient — uses kubectl with eks-token for auth.
Works in Atlantis container and locally.
"""
import subprocess
import json
import os


class EKSClient:
    def __init__(self, cluster_name: str, region: str):
        self.cluster_name = cluster_name
        self.region       = region
        self._ensure_kubeconfig()

    def _ensure_kubeconfig(self):
        """Set up kubeconfig using eks-token if not already configured."""
        import boto3, base64
        from eks_token import get_token

        try:
            eks = boto3.client('eks', region_name=self.region)
            cluster = eks.describe_cluster(name=self.cluster_name)['cluster']

            ca = base64.b64decode(cluster['certificateAuthority']['data'])
            with open('/tmp/eks-ca.crt', 'wb') as f:
                f.write(ca)

            token = get_token(cluster_name=self.cluster_name)['status']['token']

            os.makedirs(os.path.expanduser('~/.kube'), exist_ok=True)
            kubeconfig = (
                "apiVersion: v1\n"
                "clusters:\n"
                "- cluster:\n"
                "    certificate-authority: /tmp/eks-ca.crt\n"
                f"    server: {cluster['endpoint']}\n"
                f"  name: {self.cluster_name}\n"
                "contexts:\n"
                "- context:\n"
                f"    cluster: {self.cluster_name}\n"
                f"    user: {self.cluster_name}\n"
                f"  name: {self.cluster_name}\n"
                f"current-context: {self.cluster_name}\n"
                "kind: Config\n"
                "users:\n"
                f"- name: {self.cluster_name}\n"
                "  user:\n"
                f"    token: {token}\n"
            )
            with open(os.path.expanduser('~/.kube/config'), 'w') as f:
                f.write(kubeconfig)
        except Exception as e:
            print(f"[kubeconfig] Setup failed: {e}, using existing config")

    def _kubectl(self, args: list) -> dict:
        cmd = ["kubectl"] + args + ["-o", "json"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
        return json.loads(result.stdout)

    def get_nodes(self) -> list:
        data = self._kubectl(["get", "nodes"])
        nodes = []
        for n in data.get("items", []):
            labels = n["metadata"].get("labels", {})
            alloc  = n["status"].get("allocatable", {})
            nodes.append({
                "name": n["metadata"]["name"],
                "instance_type": labels.get(
                    "node.kubernetes.io/instance-type", "unknown"
                ),
                "allocatable_cpu":    self._parse_cpu(alloc.get("cpu", "0")),
                "allocatable_memory": self._parse_mem(alloc.get("memory", "0Ki")),
            })
        return nodes

    def get_pods(self, namespace: str = "all") -> list:
        SKIP = {"kube-system", "kube-public", "kube-node-lease"}
        if namespace == "all":
            data = self._kubectl(["get", "pods", "--all-namespaces"])
        else:
            data = self._kubectl(["get", "pods", "-n", namespace])
        pods = []
        for pod in data.get("items", []):
            ns = pod["metadata"].get("namespace", "default")
            if ns in SKIP:
                continue
            cpu_req = mem_req = 0
            for c in pod["spec"].get("containers", []):
                requests = c.get("resources", {}).get("requests", {})
                cpu_req += self._parse_cpu(requests.get("cpu", "0"))
                mem_req += self._parse_mem(requests.get("memory", "0Ki"))
            pods.append({
                "name":           pod["metadata"]["name"],
                "namespace":      ns,
                "deployment":     self._deployment(pod),
                "node":           pod["spec"].get("nodeName", ""),
                "phase":          pod["status"].get("phase", "Unknown"),
                "cpu_request":    cpu_req,
                "memory_request": mem_req,
            })
        return pods

    @staticmethod
    def _deployment(pod: dict) -> str:
        for ref in pod["metadata"].get("ownerReferences", []):
            if ref["kind"] == "ReplicaSet":
                parts = ref["name"].rsplit("-", 2)
                return parts[0] if len(parts) >= 2 else ref["name"]
        return pod["metadata"]["name"]

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
