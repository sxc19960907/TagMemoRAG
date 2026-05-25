from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "default_on_retained_monitoring.v1"
MANIFEST_SCHEMA_VERSION = "default_on_retained_monitoring.manifest.v1"


@dataclass(frozen=True)
class MonitoringSlice:
    name: str
    kind: str
    suite_path: str
    corpus_path: str | None
    rerun_command: str | None
    report_path: str
    min_hit_at_k: float
    min_recall_at_k: float
    min_mrr: float


@dataclass(frozen=True)
class MonitoringGate:
    name: str
    path: str


@dataclass(frozen=True)
class SliceStatus:
    name: str
    status: str
    cases: int = 0
    hit_at_k: float = 0.0
    recall_at_k: float = 0.0
    mrr: float = 0.0
    report_path: str = ""
    failed_checks: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "cases": self.cases,
            "hit_at_k": self.hit_at_k,
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "report_path": self.report_path,
            "failed_checks": list(self.failed_checks),
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class GateStatus:
    name: str
    status: str
    path: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"name": self.name, "status": self.status, "path": self.path}
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class MonitoringReport:
    status: str
    slices: list[SliceStatus]
    gates: list[GateStatus]
    failed_checks: list[str]
    next_steps: list[str]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "slices": [item.to_dict() for item in self.slices],
            "gates": [item.to_dict() for item in self.gates],
            "failed_checks": list(self.failed_checks),
            "next_steps": list(self.next_steps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# Default-On Retained Monitoring",
            "",
            f"- Status: `{self.status}`",
            "",
            "## Slices",
            "",
            "| Slice | Status | Cases | Hit@k | Recall@k | MRR |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for item in self.slices:
            lines.append(
                f"| `{item.name}` | `{item.status}` | {item.cases} | "
                f"{item.hit_at_k:.6f} | {item.recall_at_k:.6f} | {item.mrr:.6f} |"
            )
        lines.extend(["", "## Gates", "", "| Gate | Status |", "| --- | --- |"])
        lines.extend(f"| `{gate.name}` | `{gate.status}` |" for gate in self.gates)
        if self.failed_checks:
            lines.extend(["", "## Failed Checks"])
            lines.extend(f"- `{check}`" for check in self.failed_checks)
        if self.next_steps:
            lines.extend(["", "## Next Steps"])
            lines.extend(f"- {step}" for step in self.next_steps)
        return "\n".join(lines) + "\n"


def run_default_on_retained_monitoring(manifest_path: str | Path) -> MonitoringReport:
    manifest = _read_manifest(Path(manifest_path))
    slice_statuses = [_slice_status(item) for item in manifest["slices"]]
    gate_statuses = [_gate_status(item) for item in manifest["gates"]]
    failed_checks = _failed_checks(slice_statuses, gate_statuses)
    status = "passed" if not failed_checks else "failed"
    next_steps = (
        ["Default-on retained monitoring is green; expand the smallest retained slices next."]
        if status == "passed"
        else ["Do not expand ranking behavior until failed retained monitoring checks are addressed."]
    )
    return MonitoringReport(status, slice_statuses, gate_statuses, failed_checks, next_steps)


def write_monitoring_report(report: MonitoringReport, path: str | Path, *, fmt: str = "json") -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = report.to_json()
    elif fmt == "markdown":
        text = report.to_markdown()
    else:
        raise ValueError("fmt must be 'json' or 'markdown'")
    output_path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


def _read_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported monitoring manifest schema")
    return {
        "slices": [_manifest_slice(item) for item in data.get("slices") or []],
        "gates": [_manifest_gate(item) for item in data.get("gates") or []],
    }


def _manifest_slice(item: dict[str, Any]) -> MonitoringSlice:
    return MonitoringSlice(
        name=str(item["name"]),
        kind=str(item.get("kind") or "retrieval"),
        suite_path=str(item["suite_path"]),
        corpus_path=str(item["corpus_path"]) if item.get("corpus_path") is not None else None,
        rerun_command=str(item["rerun_command"]) if item.get("rerun_command") is not None else None,
        report_path=str(item["report_path"]),
        min_hit_at_k=float(item.get("min_hit_at_k", 1.0)),
        min_recall_at_k=float(item.get("min_recall_at_k", 1.0)),
        min_mrr=float(item.get("min_mrr", 0.0)),
    )


def _manifest_gate(item: dict[str, Any]) -> MonitoringGate:
    return MonitoringGate(name=str(item["name"]), path=str(item["path"]))


def _slice_status(item: MonitoringSlice) -> SliceStatus:
    data, error = _read_json(item.report_path)
    if error is not None:
        return SliceStatus(name=item.name, status="failed", report_path=item.report_path, failed_checks=["report_read"], error=error)
    summary = dict(data.get("summary") or {})
    cases = int(summary.get("cases") or 0)
    hit_at_k = _metric(summary, "hit_at_k")
    recall_at_k = _metric(summary, "recall_at_k")
    mrr = _metric(summary, "mrr")
    failed = []
    if hit_at_k + 1e-9 < item.min_hit_at_k:
        failed.append("hit_at_k")
    if recall_at_k + 1e-9 < item.min_recall_at_k:
        failed.append("recall_at_k")
    if mrr + 1e-9 < item.min_mrr:
        failed.append("mrr")
    if summary.get("passed") is False:
        failed.append("summary_passed")
    return SliceStatus(
        name=item.name,
        status="passed" if not failed else "failed",
        cases=cases,
        hit_at_k=hit_at_k,
        recall_at_k=recall_at_k,
        mrr=mrr,
        report_path=item.report_path,
        failed_checks=failed,
    )


def _gate_status(item: MonitoringGate) -> GateStatus:
    data, error = _read_json(item.path)
    if error is not None:
        return GateStatus(name=item.name, status="failed", path=item.path, error=error)
    status = str(data.get("status") or "unknown")
    return GateStatus(name=item.name, status=status, path=item.path)


def _read_json(path: str) -> tuple[dict[str, Any], str | None]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except OSError:
        return {}, "report_not_readable"
    except json.JSONDecodeError:
        return {}, "report_json_invalid"


def _metric(summary: dict[str, Any], name: str) -> float:
    return round(float(summary.get(name) or 0.0), 6)


def _failed_checks(slices: list[SliceStatus], gates: list[GateStatus]) -> list[str]:
    failed = []
    for item in slices:
        failed.extend(f"slice:{item.name}:{check}" for check in item.failed_checks)
    for item in gates:
        if item.status != "passed":
            failed.append(f"gate:{item.name}:{item.status}")
    return failed
