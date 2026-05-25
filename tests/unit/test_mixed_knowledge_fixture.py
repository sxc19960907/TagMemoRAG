from __future__ import annotations

from pathlib import Path

from tagmemorag.eval.dataset import load_eval_suite


def test_mixed_github_case_models_multi_evidence_answer_support():
    cases = {case.id: case for case in load_eval_suite(Path("tests/fixtures/eval/mixed_knowledge.jsonl"))}
    case = cases["mixed-docs-github-readme"]

    contains_sets = [set(expected.text_contains) for expected in case.relevant]

    assert len(case.relevant) >= 2
    assert any("repository as a folder that contains related items" in items for items in contains_sets)
    assert any("README files are written in Markdown" in items for items in contains_sets)
    assert case.negatives
