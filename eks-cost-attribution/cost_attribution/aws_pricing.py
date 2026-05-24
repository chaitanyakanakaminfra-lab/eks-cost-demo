"""
AWSPricing — fetches EC2 on-demand prices from AWS Price List API.
Falls back to hardcoded prices if API call fails.
"""
import boto3
import json

FALLBACK = {
    "t3.micro":   0.0104, "t3.small":   0.0208,
    "t3.medium":  0.0416, "t3.large":   0.0832,
    "t3.xlarge":  0.1664, "t3.2xlarge": 0.3328,
    "m5.large":   0.096,  "m5.xlarge":  0.192,
    "m5.2xlarge": 0.384,  "m5.4xlarge": 0.768,
    "c5.large":   0.085,  "c5.xlarge":  0.170,
    "c5.2xlarge": 0.340,  "r5.large":   0.126,
    "r5.xlarge":  0.252,
}

HOURS_PER_MONTH = 730


class AWSPricing:
    def __init__(self, region: str = "us-east-1"):
        self.region  = region
        # Pricing API only available in us-east-1
        self.client  = boto3.client("pricing", region_name="us-east-1")
        self._cache: dict[str, float] = {}

    def get_node_costs(self, nodes: list[dict]) -> dict[str, float]:
        """Return {node_name: monthly_cost_usd} for all nodes."""
        hourly = {
            itype: self._hourly_price(itype)
            for itype in set(n["instance_type"] for n in nodes)
        }
        return {
            n["name"]: hourly.get(
                n["instance_type"], 0.10
            ) * HOURS_PER_MONTH
            for n in nodes
        }

    def _hourly_price(self, instance_type: str) -> float:
        if instance_type in self._cache:
            return self._cache[instance_type]
        try:
            resp = self.client.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType",
                     "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "operatingSystem",
                     "Value": "Linux"},
                    {"Type": "TERM_MATCH", "Field": "tenancy",
                     "Value": "Shared"},
                    {"Type": "TERM_MATCH", "Field": "preInstalledSw",
                     "Value": "NA"},
                    {"Type": "TERM_MATCH", "Field": "regionCode",
                     "Value": self.region},
                ],
                MaxResults=1,
            )
            for item in resp.get("PriceList", []):
                data = json.loads(item)
                for term in data["terms"]["OnDemand"].values():
                    for dim in term["priceDimensions"].values():
                        price = float(dim["pricePerUnit"]["USD"])
                        self._cache[instance_type] = price
                        return price
        except Exception:
            pass
        fallback = FALLBACK.get(instance_type, 0.10)
        self._cache[instance_type] = fallback
        return fallback
