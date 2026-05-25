from __future__ import annotations

from pathlib import Path
import time

from tagmemorag.config import ManualLibraryConfig, ModelConfig, SearchConfig, Settings, StorageConfig, VectorStoreConfig
from tagmemorag.eval.dataset import EvalThresholds
from tagmemorag.eval.runner import run_eval
from tagmemorag.manual_library import library_root, mark_pending, upsert_manual
from tagmemorag.search_runtime import SearchExecution
from tagmemorag.state import AppState, build_kb, save_kb, start_library_rebuild
from tagmemorag.types import Result
from tests.unit.test_storage_state import FakeQdrantClient


def test_run_eval_uses_isolated_storage_by_default(tmp_path, test_config):
    test_config.model = ModelConfig(provider="hashing", dim=64)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 蒸汽\n蒸汽很小需要清洗喷嘴。\n", encoding="utf-8")
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"steam","query":"蒸汽很小","relevant":[{"source_file":"manual.md","header":"蒸汽","text_contains":["清洗喷嘴"]}]}\n',
        encoding="utf-8",
    )
    eval_data_dir = tmp_path / "eval-data"

    report = run_eval(
        cfg=test_config,
        suite_path=suite,
        docs_path=docs,
        eval_data_dir=eval_data_dir,
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )

    assert report.summary.passed
    assert (eval_data_dir / "default" / "meta.json").exists()
    assert not (Path(test_config.storage.data_dir) / "default").exists()
    assert report.config_snapshot["build_ids"]["default"]


def test_run_eval_product_manual_suite_is_reproducible(tmp_path, test_config):
    test_config.model = ModelConfig(provider="hashing", dim=64)

    report = run_eval(
        cfg=test_config,
        suite_path=Path("tests/fixtures/eval/product_manuals.jsonl"),
        docs_path=Path("tests/fixtures/product_manuals"),
        eval_data_dir=tmp_path / "eval-data",
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )

    assert report.summary.passed
    assert report.summary.cases == 14
    assert {case.id for case in report.cases} >= {"washer-e21-fault", "dishwasher-cleaning-anchor"}
    first_case = report.cases[0].to_dict()
    assert first_case["search_strategy"] == "exact_local"
    assert first_case["expected"][0]["metadata"]["manual_id"] == "fridge-nrk6192"
    assert not str(report.config_snapshot["storage"]["data_dir"]).startswith(str(test_config.storage.data_dir))


def test_run_eval_records_search_parameter_overrides(tmp_path, test_config):
    test_config.model = ModelConfig(provider="hashing", dim=64)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# Steam\nSteam pressure drops when scale blocks the nozzle.\n", encoding="utf-8")
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"steam","query":"steam pressure nozzle scale","relevant":[{"source_file":"manual.md","header":"Steam","text_contains":["scale blocks"]}]}\n',
        encoding="utf-8",
    )

    report = run_eval(
        cfg=test_config,
        suite_path=suite,
        docs_path=docs,
        top_k=4,
        source_k=4,
        steps=2,
        decay=0.55,
        amplitude_cutoff=0.02,
        aggregate="sum",
        metadata_field_boost=0.08,
        tag_boost=0.05,
        eval_data_dir=tmp_path / "eval-data",
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )

    assert report.summary.passed
    assert report.config_snapshot["search"] == {
        "top_k": 4,
        "source_k": 4,
        "steps": 2,
        "decay": 0.55,
        "amplitude_cutoff": 0.02,
        "aggregate": "sum",
        "metadata_field_boost": 0.08,
        "tag_boost": 0.05,
        "lexical_enabled": True,
        "lexical_candidate_k": 32,
        "lexical_source_k": 3,
        "lexical_min_token_chars": 2,
        "lexical_boost": 0.2,
        "lexical_exact_code_boost": 0.15,
        "lexical_model_boost": 0.12,
        "metadata_narrowing_enabled": True,
        "metadata_narrowing_brand_policy": "boost_if_not_unique",
        "metadata_narrowing_category_policy": "hard_filter_product_manual",
        "metadata_narrowing_min_candidates": 1,
        "same_page_ordering_enabled": False,
        "same_page_ordering_min_group_size": 2,
    }


def test_run_eval_same_page_ordering_default_off_preserves_pressure_order(monkeypatch, tmp_path, test_config):
    test_config.model = ModelConfig(provider="hashing", dim=64)
    docs = _write_same_page_eval_docs(tmp_path)
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"repo","query":"what is a github repository README",'
        '"relevant":[{"source_file":"github.md","text_contains":["repository is a folder"]}],'
        '"top_k_override":2}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("tagmemorag.eval.runner.execute_search", _fixed_same_page_search)

    report = run_eval(
        cfg=test_config,
        suite_path=suite,
        docs_path=docs,
        eval_data_dir=tmp_path / "eval-data",
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )

    assert report.summary.passed
    assert report.cases[0].metrics.mrr == 0.5
    assert report.cases[0].actual_top_k[0]["matched_expected_indexes"] == []
    assert report.config_snapshot["search"]["same_page_ordering_enabled"] is False


def test_run_eval_same_page_ordering_enabled_promotes_pressure_result(monkeypatch, tmp_path, test_config):
    test_config.model = ModelConfig(provider="hashing", dim=64)
    test_config.search.same_page_ordering_enabled = True
    docs = _write_same_page_eval_docs(tmp_path)
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"repo","query":"what is a github repository README",'
        '"relevant":[{"source_file":"github.md","text_contains":["repository is a folder"]}],'
        '"top_k_override":2}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("tagmemorag.eval.runner.execute_search", _fixed_same_page_search)

    report = run_eval(
        cfg=test_config,
        suite_path=suite,
        docs_path=docs,
        eval_data_dir=tmp_path / "eval-data",
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )

    assert report.summary.passed
    assert report.cases[0].metrics.mrr == 1.0
    assert report.cases[0].actual_top_k[0]["matched_expected_indexes"] == [0]
    assert report.config_snapshot["search"]["same_page_ordering_enabled"] is True


def test_run_eval_records_force_mode(tmp_path, test_config):
    test_config.model = ModelConfig(provider="hashing", dim=64)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# Steam\nSteam pressure drops when scale blocks the nozzle.\n", encoding="utf-8")
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"steam","query":"steam pressure nozzle scale","relevant":[{"source_file":"manual.md","header":"Steam","text_contains":["scale blocks"]}]}\n',
        encoding="utf-8",
    )

    report = run_eval(
        cfg=test_config,
        suite_path=suite,
        docs_path=docs,
        force_mode="agentic",
        eval_data_dir=tmp_path / "eval-data",
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )

    assert report.summary.passed
    assert report.config_snapshot["agentic"] == {"force_mode": "agentic", "mode": "agentic"}


def test_run_eval_uses_ann_preselection_with_fake_qdrant(monkeypatch, tmp_path, test_config):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    test_config.model = ModelConfig(provider="hashing", dim=64)
    test_config.vector_store = VectorStoreConfig(provider="qdrant", collection_prefix="evaltest")
    test_config.search = SearchConfig(ann_preselect_enabled=True, ann_candidate_k=3, source_k=3, steps=0)
    suite = tmp_path / "ann.jsonl"
    suite.write_text(
        '{"id":"washer-e21-ann","query":"E21 washer drain pump filter","relevant":[{"source_file":"washer/washer_wm8.md","header":"E21 Drain Fault","text_contains":["pump filter"]}],"top_k_override":5,"min_recall_at_k":0.5,"min_mrr":0.1,"min_hit_at_k":0.5}\n',
        encoding="utf-8",
    )

    report = run_eval(
        cfg=test_config,
        suite_path=suite,
        docs_path=Path("tests/fixtures/product_manuals"),
        eval_data_dir=tmp_path / "eval-data",
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )

    case = report.cases[0]
    assert case.passed
    assert case.search_strategy == "ann_preselect_then_wave"
    assert case.ann_candidate_count == 3
    assert FakeQdrantClient.search_calls


def test_incremental_rebuild_then_eval_reflects_changed_manual(tmp_path):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model=ModelConfig(provider="hashing", dim=64),
    )
    upsert_manual(
        "default",
        _manual_metadata("washer/a.md", "washer-a"),
        b"# Washer Status\nold drain filter guidance mentions alpha only.\n",
        cfg,
    )
    old_state = build_kb(library_root("default", cfg), "default", cfg)
    save_kb(old_state, cfg)
    mark_pending("default", cfg, pending=False, build_id=old_state.build_id)
    app = AppState(old_state)

    report_before = run_eval(
        cfg=cfg,
        suite_path=_write_incremental_suite(tmp_path, "old drain filter guidance"),
        reuse_built_kb=True,
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )
    assert report_before.summary.passed

    manual_path = library_root("default", cfg) / "washer" / "a.md"
    manual_path.write_text("# Washer Status\nnew drain pump reset guidance mentions bravo latch.\n", encoding="utf-8")
    mark_pending("default", cfg, dirty={"manual_id": "washer-a", "source_file": "washer/a.md", "operation": "file_replace"})
    task = start_library_rebuild(app, "default", cfg, mode="incremental")
    _wait_for_task(task)
    assert task.status == "done"
    assert task.effective_mode == "incremental"

    report_after = run_eval(
        cfg=cfg,
        suite_path=_write_incremental_suite(tmp_path, "new drain pump reset guidance"),
        reuse_built_kb=True,
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )
    assert report_after.summary.passed
    assert "new drain pump reset guidance" in report_after.cases[0].actual_top_k[0]["text"]


def _manual_metadata(source_file: str, manual_id: str) -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": "Washer A",
        "source_file": source_file,
        "product_category": "washer",
        "language": "en",
        "tags": ["maintenance"],
    }


def _write_incremental_suite(tmp_path: Path, expected_text: str) -> Path:
    suite = tmp_path / f"{expected_text.split()[0]}-suite.jsonl"
    suite.write_text(
        (
            '{"id":"incremental-washer","query":"drain pump reset washer guidance",'
            '"relevant":[{"source_file":"washer/a.md","header":"Washer Status",'
            f'"text_contains":["{expected_text}"],"metadata":{{"manual_id":"washer-a"}}}}],'
            '"top_k_override":3,"min_recall_at_k":0.5,"min_mrr":0.1,"min_hit_at_k":0.5}\n'
        ),
        encoding="utf-8",
    )
    return suite


def _write_same_page_eval_docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "github.md").write_text(
        "\n\n".join(
            [
                "# Hello World\nCreate a branch and open a pull request.",
                "# Hello World\nA repository is a folder that contains README files.",
            ]
        ),
        encoding="utf-8",
    )
    return docs


def _fixed_same_page_search(**_kwargs) -> SearchExecution:
    return SearchExecution(
        results=[
            Result(
                node_id=1,
                score=3.2,
                text="Create a branch and open a pull request.",
                header="Hello World",
                path=["Hello World"],
                source_file="github.md",
                start_line=1,
                anchor_key="top",
                metadata={"chunk_id": "top"},
            ),
            Result(
                node_id=2,
                score=3.1,
                text="A repository is a folder that contains README files.",
                header="Hello World",
                path=["Hello World"],
                source_file="github.md",
                start_line=2,
                anchor_key="matched",
                metadata={"chunk_id": "matched"},
            ),
        ],
        eligible_node_ids={1, 2},
        strategy="exact_local",
    )


def _wait_for_task(task) -> None:
    for _ in range(100):
        if task.status != "running":
            return
        time.sleep(0.01)
