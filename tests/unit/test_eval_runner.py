from __future__ import annotations

from pathlib import Path

from tagmemorag.config import ModelConfig
from tagmemorag.eval.dataset import EvalThresholds
from tagmemorag.eval.runner import run_eval


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
