from __future__ import annotations

from collections import Counter
from typing import Any

from .models import ReplayReport


def render_markdown(report: ReplayReport) -> str:
    data = report.to_dict()
    target = data["target"]
    baseline = data.get("baseline")
    lines = [
        f"# Replay Report: {data['kb']}",
        "",
        f"- Target generation: g{target.get('generation')}",
    ]
    if baseline:
        lines.append(f"- Baseline generation: g{baseline.get('generation')}")
    lines.extend([
        f"- Regression detected: {str(data['regression_detected']).lower()}",
        "",
        "## Row Counts",
        "",
    ])
    for key, value in sorted(data["row_counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Target Metrics", ""])
    lines.extend(_metric_lines(target.get("metrics") or {}))
    if baseline:
        lines.extend(["", "## Baseline Metrics", ""])
        lines.extend(_metric_lines(baseline.get("metrics") or {}))
        lines.extend(["", "## Deltas", ""])
        lines.extend(_metric_lines(data.get("deltas") or {}))
    lines.extend(["", "## Rerank Summary", ""])
    lines.extend(_metric_lines(data.get("rerank_summary") or {}))
    skipped_rows = data.get("skipped_rows") or []
    if skipped_rows:
        reason_counts = Counter(str(row.get("reason") or "unknown") for row in skipped_rows)
        lines.extend(["", "## Skipped Rows", ""])
        for reason, count in sorted(reason_counts.items()):
            lines.append(f"- {reason}: {count}")
    return "\n".join(lines).rstrip() + "\n"


def _metric_lines(metrics: dict[str, Any]) -> list[str]:
    if not metrics:
        return ["- none"]
    lines: list[str] = []
    for key, value in sorted(metrics.items()):
        if isinstance(value, dict):
            rendered = ", ".join(f"{k}={v}" for k, v in sorted(value.items())) or "{}"
            lines.append(f"- {key}: {rendered}")
        else:
            lines.append(f"- {key}: {value}")
    return lines


__all__ = ["render_markdown"]
