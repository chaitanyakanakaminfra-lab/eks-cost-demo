"""
CloudWatchMetrics — fetches actual pod CPU and memory usage.
Requires CloudWatch Container Insights enabled on EKS cluster.
Returns 0 gracefully if metrics unavailable.
"""
import boto3
from datetime import datetime, timedelta, timezone
from statistics import mean


class CloudWatchMetrics:
    def __init__(self, cluster_name: str, region: str):
        self.cluster = cluster_name
        self.client  = boto3.client("cloudwatch", region_name=region)

    def get_pod_usage(self, pods: list[dict]) -> dict[str, dict]:
        """Return {pod_name: {cpu_actual_millicores, memory_actual_mib}}."""
        end   = datetime.now(timezone.utc)
        start = end - timedelta(hours=24)
        return {
            pod["name"]: {
                "cpu_actual_millicores": self._avg(
                    "pod_cpu_utilized",
                    pod["namespace"],
                    pod["name"],
                    start, end,
                ),
                "memory_actual_mib": self._avg(
                    "pod_memory_utilized",
                    pod["namespace"],
                    pod["name"],
                    start, end,
                ),
            }
            for pod in pods
        }

    def _avg(
        self,
        metric: str,
        ns: str,
        pod: str,
        start: datetime,
        end: datetime,
    ) -> float:
        try:
            resp = self.client.get_metric_statistics(
                Namespace="ContainerInsights",
                MetricName=metric,
                Dimensions=[
                    {"Name": "ClusterName", "Value": self.cluster},
                    {"Name": "Namespace",   "Value": ns},
                    {"Name": "PodName",     "Value": pod},
                ],
                StartTime=start,
                EndTime=end,
                Period=3600,
                Statistics=["Average"],
            )
            pts = resp.get("Datapoints", [])
            return mean(d["Average"] for d in pts) if pts else 0.0
        except Exception:
            return 0.0
