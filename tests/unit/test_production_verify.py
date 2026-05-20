from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import production_verify as pv  # noqa: E402


def test_production_verify_default_local_report_is_sanitized(tmp_path):
    report = pv.run_verification(workdir=tmp_path / "verify")
    body = report.to_dict()

    assert body["schema_version"] == "production_verification.v1"
    assert body["status"] == "warning"
    steps = {step["name"]: step for step in body["steps"]}
    assert steps["config_validate"]["status"] == "passed"
    assert steps["provider_probe"]["status"] == "skipped"
    assert steps["readiness_smoke"]["status"] == "passed"
    assert steps["pilot_run"]["status"] == "warning"

    serialized = json.dumps(body, ensure_ascii=False)
    assert "Authorization" not in serialized
    assert "蒸汽很小怎么办" not in serialized
    assert "actual_top_k" not in serialized


def test_production_verify_main_writes_markdown(tmp_path, capsys):
    output = tmp_path / "report.md"

    exit_code = pv.main([
        "--workdir",
        str(tmp_path / "verify"),
        "--format",
        "markdown",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    rendered = output.read_text(encoding="utf-8")
    assert rendered.startswith("# Production Environment Verification")
    assert "| `provider_probe` | `skipped` |" in rendered


def test_production_verify_explicit_probe_selection(monkeypatch, tmp_path):
    seen = {}
    original_probe = pv.run_provider_probe

    def _fake_probe(config_path, *, selected, kb_name="default"):
        seen["config_path"] = config_path
        seen["selected"] = selected
        return original_probe("examples/config/local-hashing-npz.yaml", selected=[])

    monkeypatch.setattr(pv, "run_provider_probe", _fake_probe)

    report = pv.run_verification(
        workdir=tmp_path / "verify",
        probes=["embedding,qdrant"],
    )

    step = next(step for step in report.steps if step.name == "provider_probe")
    assert seen["selected"] == ["embedding", "qdrant"]
    assert step.status == "skipped"
    assert step.detail["selected"] == ["embedding", "qdrant"]
