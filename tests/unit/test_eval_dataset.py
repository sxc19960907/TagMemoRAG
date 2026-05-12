from __future__ import annotations

import pytest

from tagmemorag.eval.dataset import EvalSuiteError, load_eval_suite


def test_load_eval_suite_valid(tmp_path):
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"case-1","query":"蒸汽很小","relevant":[{"source_file":"manual.md","text_contains":["蒸汽"]}]}\n',
        encoding="utf-8",
    )

    cases = load_eval_suite(suite)

    assert len(cases) == 1
    assert cases[0].id == "case-1"
    assert cases[0].kb_name == "default"
    assert cases[0].relevant[0].text_contains == ("蒸汽",)


def test_load_eval_suite_reports_line_number_for_bad_json(tmp_path):
    suite = tmp_path / "suite.jsonl"
    suite.write_text('{"id":"ok","query":"q","relevant":[{"header":"h"}]}\n{bad\n', encoding="utf-8")

    with pytest.raises(EvalSuiteError, match=r"suite\.jsonl:2: invalid JSON"):
        load_eval_suite(suite)


def test_load_eval_suite_rejects_duplicate_id(tmp_path):
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        "\n".join(
            [
                '{"id":"dup","query":"q1","relevant":[{"header":"h"}]}',
                '{"id":"dup","query":"q2","relevant":[{"header":"h"}]}',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(EvalSuiteError, match="duplicate case id: dup"):
        load_eval_suite(suite)


def test_load_eval_suite_rejects_empty_relevant(tmp_path):
    suite = tmp_path / "suite.jsonl"
    suite.write_text('{"id":"case-1","query":"q","relevant":[]}\n', encoding="utf-8")

    with pytest.raises(EvalSuiteError, match="non-empty relevant"):
        load_eval_suite(suite)


def test_load_eval_suite_rejects_missing_matcher_field(tmp_path):
    suite = tmp_path / "suite.jsonl"
    suite.write_text('{"id":"case-1","query":"q","relevant":[{"weight":1.0}]}\n', encoding="utf-8")

    with pytest.raises(EvalSuiteError, match="at least one matcher field"):
        load_eval_suite(suite)


def test_load_eval_suite_rejects_invalid_threshold(tmp_path):
    suite = tmp_path / "suite.jsonl"
    suite.write_text('{"id":"case-1","query":"q","min_mrr":1.5,"relevant":[{"header":"h"}]}\n', encoding="utf-8")

    with pytest.raises(EvalSuiteError, match="min_mrr must be between"):
        load_eval_suite(suite)
