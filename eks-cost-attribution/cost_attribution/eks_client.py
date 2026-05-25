"""
EKSClient — works both locally (kubectl) and in Atlantis (boto3 token).
"""
import subprocess
import json
import os


class EKSClient:
    def __init__(self, cluster_name: str, region: str):
        self.cluster_name = cluster_name
        self.region       = region

    def _kubectl(self, args: list) -> dict:
        env = os.environ.copy()
        # Try to generate kubeconfig if not present
        if not os.path.exists(os.path.expanduser('~/.kube/config')):
            self._setup_kubeconfig()
        cmd = ["kubectl"] + args + ["-o", "json"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, env=env
        )
        return json.loads(result.stdout)

    def _setup_kubeconfig(self):
        """Generate kubeconfig using boto3 when aws cli not available."""
        import boto3, base64, tempfile
        from botocore.signers import RequestSigner
        from botocore.credentials import Credentials

        session = boto3.session.Session()
        eks = session.client('eks', region_name=self.region)
        cluster = eks.describe_cluster(name=self.cluster_name)['cluster']

        # Write CA
        ca = base64.b64decode(cluster['certificateAuthority']['data'])
        ca_file = '/tmp/eks-ca.crt'
        with open(ca_file, 'wb') as f:
            f.write(ca)

        # Generate token using STS presigned URL (correct EKS format)
        service_id = 'sts'
        signer = RequestSigner(
            service_id,
            self.region,
            'sts',
            'v4',
            session.get_credentials(),
            session.get_component('event_emitter')
        )
        import botocore.awsrequest
        params = {
            'method': 'GET',
            'url': f'https://sts.{self.region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
            'body': {},
            'headers': {'x-k8s-aws-id': self.cluster_name},
            'context': {}
        }
        signed = signer.generate_presigned_url(
            params, region_name=self.region,
            expires_in=60, operation_name=''
        )
        token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(
            signed.encode()
        ).decode().rstrip('=')

        # Write kubeconfig
        kubeconfig = f"""apiVersion: v1
clusters:
- cluster:
    certificate-authority: {ca_file}
    server: {cluster['endpoint']}
  name: {self.cluster_name}
contexts:
- context:
    cluster: {self.cluster_name}
    user: {self.cluster_name}
  name: {self.cluster_name}
current-context: {self.cluster_name}
kind: Config
users:
- name: {self.cluster_name}
  user:
    token: {token}
"""
        os.makedirs(os.path.expanduser('~/.kube'), exist_ok=True)
        with open(os.path.expanduser('~/.kube/config'), 'w') as f:
            f.write(kubeconfig)

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
