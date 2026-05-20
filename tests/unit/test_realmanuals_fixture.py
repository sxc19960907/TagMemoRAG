from __future__ import annotations

from pathlib import Path

from tagmemorag.eval.dataset import load_eval_suite


def test_realmanuals_fixture_has_strict_ground_truth():
    cases = load_eval_suite(Path("tests/fixtures/eval/realmanuals.jsonl"))

    assert len(cases) >= 8
    for case in cases:
        for expected in case.relevant:
            assert "__PLACEHOLDER__" not in expected.text_contains
            assert expected.source_file
            assert expected.text_contains
            assert expected.metadata
            assert "manual_id" in expected.metadata
            assert "product_model" in expected.metadata
