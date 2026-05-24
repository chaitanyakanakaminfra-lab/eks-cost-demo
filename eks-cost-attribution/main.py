#!/usr/bin/env python3
"""
EKS Cost Attribution Engine
Breaks down EKS cluster bill by namespace, deployment, and pod.
"""
import click
from dotenv import load_dotenv

load_dotenv()

from cost_attribution.eks_client    import EKSClient
from cost_attribution.aws_pricing   import AWSPricing
from cost_attribution.cloudwatch    import CloudWatchMetrics
from cost_attribution.analyzer      import CostAnalyzer
from cost_attribution.reporter      import Reporter
from cost_attribution.atlantis_hook import AtlantisHook


@click.command()
@click.option("--cluster",         required=True,  help="EKS cluster name")
@click.option("--region",          default="us-east-1", show_default=True)
@click.option("--namespace",       default="all")
@click.option("--format", "fmt",   default="table",
              type=click.Choice(["table", "json", "markdown"]))
@click.option("--atlantis",        is_flag=True)
@click.option("--idle-days",       default=14,   type=int)
@click.option("--waste-threshold", default=50.0, type=float)
def main(cluster, region, namespace, fmt, atlantis, idle_days, waste_threshold):
    """Break down EKS cluster costs by namespace, deployment, and pod."""

    click.echo(f"[1/5] Connecting to EKS cluster: {cluster} ({region})...")
    eks   = EKSClient(cluster_name=cluster, region=region)
    nodes = eks.get_nodes()
    pods  = eks.get_pods(namespace=namespace)
    click.echo(f"      Found {len(nodes)} nodes, {len(pods)} pods")

    click.echo(f"[2/5] Fetching EC2 pricing...")
    pricing    = AWSPricing(region=region)
    node_costs = pricing.get_node_costs(nodes)

    click.echo(f"[3/5] Pulling CloudWatch metrics...")
    cw         = CloudWatchMetrics(cluster_name=cluster, region=region)
    usage_data = cw.get_pod_usage(pods)

    click.echo(f"[4/5] Calculating cost attribution...")
    analyzer = CostAnalyzer(
        nodes=nodes,
        pods=pods,
        node_costs=node_costs,
        usage_data=usage_data,
        idle_days=idle_days,
        waste_threshold=waste_threshold,
    )
    report   = analyzer.generate_report()

    click.echo(f"[5/5] Rendering output...")
    reporter = Reporter(report)

    if fmt == "table":
        reporter.print_table()
    elif fmt == "json":
        reporter.print_json()
    elif fmt == "markdown":
        click.echo(reporter.to_markdown())

    if atlantis:
        AtlantisHook().post_comment(reporter.to_markdown())


if __name__ == "__main__":
    main()
