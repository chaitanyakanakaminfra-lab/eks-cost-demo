"""
Reporter — formats results as rich terminal tables, JSON, or Markdown.
"""
import json
from rich.console import Console
from rich.table   import Table
from rich.panel   import Panel
from rich.text    import Text
from rich         import box
from .analyzer    import ClusterReport


class Reporter:
    def __init__(self, report: ClusterReport):
        self.r       = report
        self.console = Console()

    def print_table(self):
        r   = self.r
        hdr = Text()
        hdr.append("EKS COST ATTRIBUTION REPORT\n", style="bold white")
        hdr.append(f"Cluster total: ${r.total_monthly_cost:,.0f}/month  ",
                   style="yellow")
        hdr.append(f"Waste: {r.total_waste_pct:.0f}%  ", style="red")
        hdr.append(f"Savings: ${r.potential_savings:,.0f}/month",
                   style="green")
        self.console.print(Panel(hdr, border_style="blue"))

        t = Table(
            title="Namespace Breakdown",
            box=box.ROUNDED,
            border_style="blue",
            header_style="bold cyan",
        )
        t.add_column("Namespace",    min_width=20)
        t.add_column("Cost/Month",   justify="right", style="yellow")
        t.add_column("% of Total",   justify="right")
        t.add_column("Waste %",      justify="right")
        t.add_column("Top Issue")

        for ns in r.namespaces:
            pct    = (ns.monthly_cost / r.total_monthly_cost * 100
                      if r.total_monthly_cost else 0)
            wstyle = ("red"    if ns.waste_pct > 50
                      else "yellow" if ns.waste_pct > 20
                      else "green")
            issue  = ""
            if ns.pods:
                worst = max(ns.pods, key=lambda p: p.waste_pct)
                if worst.is_idle:
                    issue = f"{worst.deployment} (idle)"
                elif worst.waste_pct > 50:
                    issue = f"{worst.deployment} ({worst.waste_pct:.0f}% waste)"
            t.add_row(
                ns.name,
                f"${ns.monthly_cost:,.0f}",
                f"{pct:.0f}%",
                Text(f"{ns.waste_pct:.0f}%", style=wstyle),
                issue,
            )
        self.console.print(t)

        if r.idle_workloads:
            it = Table(
                title=f"Idle Workloads — {len(r.idle_workloads)} Delete Candidates",
                box=box.ROUNDED,
                border_style="red",
                header_style="bold red",
            )
            it.add_column("Namespace")
            it.add_column("Deployment")
            it.add_column("Cost/Month", justify="right", style="yellow")
            for pod in r.idle_workloads:
                it.add_row(
                    pod.namespace,
                    pod.deployment,
                    f"${pod.monthly_cost:,.0f}",
                )
            self.console.print(it)

    def to_markdown(self) -> str:
        r     = self.r
        lines = [
            "## 💰 EKS Cost Attribution Report",
            f"**Total:** ${r.total_monthly_cost:,.0f}/month  "
            f"**Waste:** {r.total_waste_pct:.0f}%  "
            f"**Savings:** ${r.potential_savings:,.0f}/month",
            "",
            "| Namespace | Cost/Month | Waste % | Issue |",
            "|-----------|-----------|---------|-------|",
        ]
        for ns in r.namespaces:
            pct  = (ns.monthly_cost / r.total_monthly_cost * 100
                    if r.total_monthly_cost else 0)
            icon = ("🔴" if ns.waste_pct > 50
                    else "🟡" if ns.waste_pct > 20
                    else "✅")
            issue = ""
            if ns.pods:
                worst     = max(ns.pods, key=lambda p: p.waste_pct)
                idle_lbl  = "idle" if worst.is_idle else f"{worst.waste_pct:.0f}% waste"
                issue     = f"{worst.deployment} ({idle_lbl})"
            lines.append(
                f"| {ns.name} | ${ns.monthly_cost:,.0f} ({pct:.0f}%) "
                f"| {icon} {ns.waste_pct:.0f}% | {issue} |"
            )
        if r.idle_workloads:
            lines += [
                "",
                "### ⛔ Idle Workloads — Delete Candidates",
                "| Namespace | Deployment | Cost/Month |",
                "|-----------|-----------|-----------|",
            ]
            for p in r.idle_workloads:
                lines.append(
                    f"| {p.namespace} | {p.deployment} | ${p.monthly_cost:,.0f} |"
                )
        return "\n".join(lines)

    def print_json(self):
        r = self.r
        print(json.dumps({
            "total_monthly_cost": r.total_monthly_cost,
            "total_waste_pct":    r.total_waste_pct,
            "potential_savings":  r.potential_savings,
            "namespaces": [
                {
                    "name":         ns.name,
                    "monthly_cost": ns.monthly_cost,
                    "waste_pct":    ns.waste_pct,
                }
                for ns in r.namespaces
            ],
            "idle_workloads": [
                {
                    "namespace":    p.namespace,
                    "deployment":   p.deployment,
                    "monthly_cost": p.monthly_cost,
                }
                for p in r.idle_workloads
            ],
        }, indent=2))
