from __future__ import annotations

import json
import subprocess
import sys

from tagmemorag import cli
from tagmemorag import readiness


def test_cli_build_and_search_with_hashing_embedder(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text(
        "# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n# 故障\nE05 表示蒸汽异常。\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
""",
        encoding="utf-8",
    )
    build = subprocess.run(
        [sys.executable, "-m", "tagmemorag", "build", "--docs", str(docs), "--config", str(config)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(build.stdout)["chunks"] == 3

    search = subprocess.run(
        [sys.executable, "-m", "tagmemorag", "search", "蒸汽很小", "--config", str(config), "--top-k", "3"],
        check=True,
        text=True,
        capture_output=True,
    )
    body = json.loads(search.stdout)
    assert body["results"]
    assert "debug" not in body
    assert any("蒸汽" in result["text"] or "E05" in result["text"] for result in body["results"])


def test_cli_config_validate_outputs_json_and_exit_code(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )

    exit_code = cli.main(["config", "validate", "--config", str(config)])

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["schema_version"] == "config_validation.v1"
    assert body["status"] == "passed"
    assert body["config_path"] == str(config)


def test_cli_config_validate_failed_report_returns_one(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  provider: http
  name: remote
  dim: 64
  api_key_env: TMR_ABSENT_FOR_CLI_TEST
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )

    exit_code = cli.main(["config", "validate", "--config", str(config)])

    assert exit_code == 1
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "failed"
    assert "TMR_ABSENT_FOR_CLI_TEST" in json.dumps(body)


def test_cli_provider_probe_all_skipped_for_local_profile(capsys):
    exit_code = cli.main(["provider", "probe", "--config", "examples/config/local-hashing-npz.yaml", "--all"])

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["schema_version"] == "provider_probe.v1"
    assert body["status"] == "skipped"
    assert {probe["status"] for probe in body["probes"]} == {"skipped"}


def test_cli_provider_probe_failed_returns_one(tmp_path, capsys):
    config = tmp_path / "answer.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
answer:
  enabled: true
  provider: openai_compatible
  model_id: model
  api_key_env: TMR_ABSENT_PROVIDER_PROBE_KEY
""",
        encoding="utf-8",
    )

    exit_code = cli.main(["provider", "probe", "--config", str(config), "--answer"])

    assert exit_code == 1
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "failed"
    assert body["probes"][0]["detail"]["env"] == "TMR_ABSENT_PROVIDER_PROBE_KEY"


def test_cli_readiness_smoke_succeeds_and_keeps_workdir(tmp_path, capsys):
    workdir = tmp_path / "smoke"

    exit_code = cli.main(["readiness", "smoke", "--workdir", str(workdir), "--keep-workdir"])

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["schema_version"] == "readiness_smoke.v1"
    assert body["status"] == "passed"
    assert body["workdir"] == str(workdir.resolve())
    checks = {check["name"]: check for check in body["checks"]}
    assert checks["build"]["detail"]["chunks"] >= 1
    assert checks["retrieve_answer"]["detail"]["evidence_count"] >= 1
    assert checks["queryplan"]["detail"]["rows"] == 1
    assert checks["bundle_roundtrip"]["detail"]["imported_manuals"] == 1
    assert (workdir / "data").exists()


def test_cli_readiness_smoke_failure_is_bounded(monkeypatch, capsys):
    def _failed_smoke(*, workdir=None, keep_workdir=False):
        return readiness.SmokeReport(
            status="failed",
            checks=[
                readiness.SmokeCheck(
                    "build",
                    "failed",
                    error={"type": "ReadinessSmokeError", "reason": "no_chunks_built"},
                )
            ],
            workdir="/tmp/tagmemorag-readiness-test",
        )

    monkeypatch.setattr(cli, "run_readiness_smoke", _failed_smoke)

    exit_code = cli.main(["readiness", "smoke"])

    assert exit_code == 1
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "failed"
    assert body["checks"][0]["error"]["reason"] == "no_chunks_built"
    serialized = json.dumps(body)
    assert "storage_key" not in serialized
    assert "checksum" not in serialized


def test_cli_pilot_run_outputs_json_file(monkeypatch, tmp_path, capsys):
    from tagmemorag.production_pilot import PilotStage, ProductionPilotReport

    def _fake_pilot(**_kwargs):
        return ProductionPilotReport(
            status="passed",
            config_path="config.yaml",
            suite_path="suite.jsonl",
            docs_path="docs",
            workdir=str(tmp_path / "pilot"),
            stages=[PilotStage("eval", "passed", {"cases": 1})],
            next_steps=["Retain the pilot report."],
        )

    monkeypatch.setattr(cli, "run_production_pilot", _fake_pilot)
    output = tmp_path / "pilot.json"

    exit_code = cli.main(["pilot", "run", "--output", str(output)])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    body = json.loads(output.read_text(encoding="utf-8"))
    assert body["schema_version"] == "production_pilot.v1"
    assert body["status"] == "passed"


def test_cli_pilot_run_markdown_failure_returns_one(monkeypatch, capsys):
    from tagmemorag.production_pilot import PilotStage, ProductionPilotReport

    def _fake_pilot(**_kwargs):
        return ProductionPilotReport(
            status="failed",
            config_path="config.yaml",
            suite_path="suite.jsonl",
            docs_path="docs",
            workdir="/tmp/pilot",
            stages=[PilotStage("eval", "failed", {"cases": 1}, {"type": "EvalThreshold", "reason": "low recall"})],
            next_steps=["Investigate failed stage(s): eval."],
        )

    monkeypatch.setattr(cli, "run_production_pilot", _fake_pilot)

    exit_code = cli.main(["pilot", "run", "--format", "markdown"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "# TagMemoRAG Production Pilot Report" in output
    assert "`failed`" in output


def test_readiness_smoke_retains_auto_workdir_on_failure(monkeypatch):
    monkeypatch.setattr(readiness, "build_kb", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    report = readiness.run_readiness_smoke()

    assert report.status == "failed"
    assert report.workdir is not None
    assert report.checks[0].name == "unexpected"
    assert report.checks[0].error["type"] == "RuntimeError"
    assert (readiness.Path(report.workdir) / "docs").exists()


def test_cli_retrain_residuals_reports_rows(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    (docs / "manual.metadata.json").write_text(
        '{"manual_id":"m1","title":"m1","source_file":"manual.md","product_category":"coffee","tags":["Steam","Wand"]}',
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
manual_library:
  registry_path: {tmp_path / "manual_registry.sqlite3"}
""",
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, "-m", "tagmemorag", "build", "--docs", str(docs), "--config", str(config)],
        check=True,
        text=True,
        capture_output=True,
    )

    result = subprocess.run(
        [sys.executable, "-m", "tagmemorag", "retrain-residuals", "--config", str(config)],
        check=True,
        text=True,
        capture_output=True,
    )

    body = json.loads(result.stdout)
    assert body["tag_intrinsic_residual_rows"] == 2


def test_cli_search_filters_manual_metadata(tmp_path):
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "coffee").mkdir()
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","product_category":"fridge","product_model":"NRK6192","language":"zh-CN","tags":["temperature-setting"]}',
        encoding="utf-8",
    )
    (docs / "coffee" / "manual.md").write_text("# 温度\n咖啡温度和蒸汽设置。\n", encoding="utf-8")
    (docs / "coffee" / "manual.metadata.json").write_text(
        '{"manual_id":"coffee-manual","title":"Coffee Manual","source_file":"coffee/manual.md","product_category":"coffee","product_model":"CM1","language":"zh-CN","tags":["maintenance"]}',
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
""",
        encoding="utf-8",
    )

    subprocess.run(
        [sys.executable, "-m", "tagmemorag", "build", "--docs", str(docs), "--config", str(config)],
        check=True,
        text=True,
        capture_output=True,
    )
    search = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "search",
            "温度",
            "--config",
            str(config),
            "--category",
            "fridge",
            "--model",
            "NRK6192",
            "--tag",
            "Temperature Setting",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    body = json.loads(search.stdout)
    assert body["results"]
    assert {result["manual_id"] for result in body["results"]} == {"fridge-manual"}


def test_cli_search_auto_narrows_by_model_metadata(tmp_path):
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "coffee").mkdir()
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","brand":"Gorenje","product_category":"fridge","product_model":"NRK6192","language":"zh-CN","tags":["temperature-setting"]}',
        encoding="utf-8",
    )
    (docs / "coffee" / "manual.md").write_text("# 温度\n咖啡温度和蒸汽设置。\n", encoding="utf-8")
    (docs / "coffee" / "manual.metadata.json").write_text(
        '{"manual_id":"coffee-manual","title":"Coffee Manual","source_file":"coffee/manual.md","brand":"Acme","product_category":"coffee","product_model":"CM1","language":"zh-CN","tags":["maintenance"]}',
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
""",
        encoding="utf-8",
    )

    subprocess.run(
        [sys.executable, "-m", "tagmemorag", "build", "--docs", str(docs), "--config", str(config)],
        check=True,
        text=True,
        capture_output=True,
    )
    search = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "search",
            "NRK6192 温度怎么调",
            "--config",
            str(config),
            "--top-k",
            "5",
            "--debug-search",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    body = json.loads(search.stdout)
    assert body["results"]
    assert {result["manual_id"] for result in body["results"]} == {"fridge-manual"}
    assert body["debug"]["metadata_narrowing"]["hard_filters"] == {"product_model": "NRK6192"}


def test_cli_search_debug_outputs_operator_metadata(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
""",
        encoding="utf-8",
    )

    subprocess.run(
        [sys.executable, "-m", "tagmemorag", "build", "--docs", str(docs), "--config", str(config)],
        check=True,
        text=True,
        capture_output=True,
    )
    search = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "search",
            "蒸汽很小",
            "--config",
            str(config),
            "--top-k",
            "3",
            "--debug-search",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    body = json.loads(search.stdout)
    assert body["debug"]["search_strategy"] == "exact_local"
    assert body["debug"]["ann_enabled"] is False
    assert body["debug"]["ann_candidate_count"] == 0
    assert body["debug"]["ann_fallback_reason"] == ""
    assert body["debug"]["lexical_enabled"] is True
    assert "lexical_candidate_count" in body["debug"]
    assert "lexical_source_count" in body["debug"]
    assert body["debug"]["lexical_profile"] == "source_boost"
    assert body["debug"]["metadata_narrowing"]["mode"] == "none"


def test_cli_search_with_ann_preselection_qdrant(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text(
        "# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n# 故障\nE05 表示蒸汽异常。\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
vector_store:
  provider: qdrant
search:
  ann_preselect_enabled: true
  ann_candidate_k: 2
""",
        encoding="utf-8",
    )

    from tests.unit.test_storage_state import FakeQdrantClient

    FakeQdrantClient.reset()
    from tagmemorag.storage import qdrant_vector

    original = qdrant_vector.QdrantVectorStore._create_client
    qdrant_vector.QdrantVectorStore._create_client = staticmethod(lambda *args, **kwargs: FakeQdrantClient())
    try:
        build = cli.main(["build", "--docs", str(docs), "--config", str(config)])
        assert build == 0
        search = cli.main(["search", "蒸汽很小", "--config", str(config), "--top-k", "3"])
        assert search == 0
    finally:
        qdrant_vector.QdrantVectorStore._create_client = original


def test_cli_eval_run_accepts_search_parameter_overrides(tmp_path, capsys):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# Steam\nSteam pressure drops when scale blocks the nozzle.\n", encoding="utf-8")
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"steam","query":"steam pressure nozzle scale","relevant":[{"source_file":"manual.md","header":"Steam","text_contains":["scale blocks"]}]}\n',
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
""",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    assert (
        cli.main(
            [
                "eval",
                "run",
                "--suite",
                str(suite),
                "--docs",
                str(docs),
                "--config",
                str(config),
                "--output",
                str(output),
                "--top-k",
                "4",
                "--source-k",
                "4",
                "--steps",
                "2",
                "--decay",
                "0.55",
                "--amplitude-cutoff",
                "0.02",
                "--aggregate",
                "sum",
                "--metadata-field-boost",
                "0.08",
                "--tag-boost",
                "0.05",
                "--eval-data-dir",
                str(tmp_path / "eval-data"),
                "--min-recall-at-k",
                "0",
                "--min-mrr",
                "0",
                "--min-hit-at-k",
                "0",
            ]
        )
        == 0
    )
    capsys.readouterr()

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["config_snapshot"]["search"]["source_k"] == 4
    assert report["config_snapshot"]["search"]["aggregate"] == "sum"
    assert report["config_snapshot"]["search"]["metadata_field_boost"] == 0.08


def test_cli_qdrant_inspect_outputs_safe_report(tmp_path, capsys, monkeypatch, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
vector_store:
  provider: qdrant
  collection_prefix: cli
""",
        encoding="utf-8",
    )

    from tests.unit.test_storage_state import FakeQdrantClient
    from tagmemorag.storage import qdrant_vector

    FakeQdrantClient.reset()
    monkeypatch.setattr(qdrant_vector.QdrantVectorStore, "_create_client", staticmethod(lambda *args, **kwargs: FakeQdrantClient()))
    assert cli.main(["build", "--docs", str(docs), "--config", str(config)]) == 0
    capsys.readouterr()

    assert cli.main(["qdrant", "inspect", "--config", str(config)]) == 0
    body = json.loads(capsys.readouterr().out)

    assert body["collection_name"] == "cli_default"
    assert body["collection_exists"] is True
    assert body["graph_node_count"] == 1
    assert body["qdrant_point_count"] == 1
    assert "sample_payload_keys" in body


def test_cli_serve_uses_config_host_port(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
model:
  name: hashing
server:
  host: 127.0.0.9
  port: 9000
""",
        encoding="utf-8",
    )
    called = {}

    def fake_run(app, **kwargs):
        called["app"] = app
        called["kwargs"] = kwargs

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)

    assert cli.main(["serve", "--config", str(config)]) == 0
    assert called["kwargs"]["host"] == "127.0.0.9"
    assert called["kwargs"]["port"] == 9000


def test_cli_auth_generate_key_outputs_hash_and_plaintext(capsys):
    assert cli.main(["auth", "generate-key", "--id", "cs-test", "--scopes", "search,rebuild", "--kb", "default", "--rate", "10"]) == 0

    out = capsys.readouterr().out
    assert '"id": "cs-test"' in out
    assert '"hash": "sha256:' in out
    assert '"scopes": [' in out
    assert "tmr_live_" in out


def test_cli_manual_bulk_preview_and_import(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
""",
        encoding="utf-8",
    )
    metadata = tmp_path / "manuals.csv"
    metadata.write_text(
        "manual_id,title,source_file,product_category,language,tags\n"
        "cm1,CM1 Manual,coffee/cm1.md,coffee,zh-CN,maintenance\n",
        encoding="utf-8",
    )
    source = tmp_path / "cm1.md"
    source.write_text("# Use\nClean weekly.\n", encoding="utf-8")

    assert cli.main(["manual-bulk", "preview", "--config", str(config), "--metadata", str(metadata), "--file", str(source)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["summary"]["valid_count"] == 1
    assert preview["rows"][0]["action"] == "create"

    assert (
        cli.main(
            [
                "manual-bulk",
                "import",
                "--config",
                str(config),
                "--metadata",
                str(metadata),
                "--file",
                str(source),
                "--selected-row",
                "2",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["imported_count"] == 1


def test_cli_manual_library_registry_commands(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  registry_backend: sqlite
  registry_path: {tmp_path / "registry.sqlite3"}
  blob_backend: local
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )
    manual_dir = tmp_path / "manuals" / "default" / "coffee"
    manual_dir.mkdir(parents=True)
    (manual_dir / "cm1.md").write_text("# Use\nClean weekly.\n", encoding="utf-8")
    (manual_dir / "cm1.metadata.json").write_text(
        '{"manual_id":"cm1","title":"CM1","source_file":"coffee/cm1.md","product_category":"coffee","language":"zh-CN"}',
        encoding="utf-8",
    )

    assert cli.main(["manual-library", "registry", "migrate", "--config", str(config), "--dry-run"]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["dry_run"] is True
    assert dry_run["imported_records"] == 1

    assert cli.main(["manual-library", "registry", "migrate", "--config", str(config)]) == 0
    committed = json.loads(capsys.readouterr().out)
    assert committed["imported_records"] == 1

    assert cli.main(["manual-library", "registry", "inspect", "--config", str(config)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["record_count"] == 1

    assert cli.main(["manual-library", "registry", "verify-blobs", "--config", str(config)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["missing_count"] == 0
    assert (tmp_path / "manuals" / "default" / "coffee" / "cm1.md").exists()

    assert cli.main(["manual-library", "registry", "migrate", "--config", str(config)]) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["skipped_records"] == 1


def test_cli_manual_library_bundle_export_inspect_import(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    restore_config = tmp_path / "restore.yaml"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
""",
        encoding="utf-8",
    )
    restore_config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "restore-data"}
manual_library:
  root_dir: {tmp_path / "restore-manuals"}
""",
        encoding="utf-8",
    )
    manual_dir = tmp_path / "manuals" / "default" / "coffee"
    manual_dir.mkdir(parents=True)
    (manual_dir / "cm1.md").write_text("# Use\nClean weekly.\n", encoding="utf-8")
    (manual_dir / "cm1.metadata.json").write_text(
        '{"manual_id":"cm1","title":"CM1","source_file":"coffee/cm1.md","product_category":"coffee","language":"zh-CN"}',
        encoding="utf-8",
    )
    bundle = tmp_path / "default.bundle.zip"

    assert cli.main(["manual-library", "bundle", "export", "--config", str(config), "--output", str(bundle)]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["manual_count"] == 1
    assert bundle.exists()

    assert cli.main(["manual-library", "bundle", "inspect", "--bundle", str(bundle), "--config", str(restore_config), "--target-kb", "restored"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["valid"] is True
    assert inspected["import_actions"][0]["action"] == "create"

    assert cli.main(["manual-library", "bundle", "import", "--bundle", str(bundle), "--config", str(restore_config), "--target-kb", "restored", "--dry-run"]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["dry_run"] is True
    assert dry_run["imported_count"] == 0

    assert cli.main(["manual-library", "bundle", "import", "--bundle", str(bundle), "--config", str(restore_config), "--target-kb", "restored"]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["imported_count"] == 1
    assert (tmp_path / "restore-manuals" / "restored" / "coffee" / "cm1.md").exists()


def test_cli_feedback_workflow(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
""",
        encoding="utf-8",
    )
    payload_path = tmp_path / "feedback.json"
    payload_path.write_text(
        json.dumps(
            {
                "feedback_id": "fb-cli",
                "trace_id": "trace-1",
                "search_id": "search-1",
                "build_id": "build-1",
                "query": "E05 蒸汽异常怎么处理",
                "outcome": "missing_result",
                "expected": [{"source_file": "coffee.md", "header": "E05", "metadata": {"manual_id": "cm1"}}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert cli.main(["feedback", "submit", "--config", str(config), "--json", str(payload_path)]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["feedback"]["feedback_id"] == "fb-cli"

    assert cli.main(["feedback", "list", "--config", str(config), "--status", "new"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [row["feedback_id"] for row in listed["feedback"]] == ["fb-cli"]

    assert cli.main(["feedback", "review", "--config", str(config), "--feedback-id", "fb-cli", "--status", "triaged"]) == 0
    reviewed = json.loads(capsys.readouterr().out)
    assert reviewed["feedback"]["status"] == "triaged"

    output = tmp_path / "eval_drafts" / "default" / "feedback.jsonl"
    assert cli.main(["feedback", "promote-preview", "--config", str(config), "--feedback-id", "fb-cli", "--output", str(output)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["cases"][0]["id"] == "feedback-fb-cli"
