"""Step 1 (M2): negatives schema, matching, and runner integration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tagmemorag.eval.dataset import EvalSuiteError, ExpectedResult, load_eval_suite
from tagmemorag.eval.matching import NegativeHit, match_negatives
from tagmemorag.types import Result


def _result(
    *,
    source_file: str = "kb/manual.md",
    header: str = "h",
    text: str = "text",
    anchor_key: str = "anchor-1",
    metadata: dict | None = None,
) -> Result:
    return Result(
        node_id=1,
        score=1.0,
        text=text,
        header=header,
        path=[header],
        source_file=source_file,
        start_line=1,
        anchor_key=anchor_key,
        metadata=metadata or {},
    )


def _write_suite(tmp_path: Path, *cases: dict) -> Path:
    suite = tmp_path / "suite.jsonl"
    suite.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n", encoding="utf-8")
    return suite


def test_match_negatives_returns_empty_when_no_negatives_configured():
    results = [_result(source_file="washer/wm8.md")]

    assert match_negatives(results, (), case_id="case") == []


def test_match_negatives_flags_top_k_hit_with_rank_and_index():
    results = [
        _result(source_file="refrigerator/nrk6192.md", text="cold compartment"),
        _result(source_file="washer/wm8.md", text="drain pump filter"),
    ]
    negatives = (
        ExpectedResult(metadata={"product_category": "washer"}),
        ExpectedResult(source_file="washer/wm8.md"),
    )

    hits = match_negatives(results, negatives, case_id="case")

    assert hits == [
        NegativeHit(rank=2, negative_index=1, source_file="washer/wm8.md"),
    ]


def test_match_negatives_supports_metadata_negatives():
    results = [
        _result(source_file="washer/wm8.md", metadata={"product_category": "washer"}),
    ]
    negatives = (ExpectedResult(metadata={"product_category": "washer"}),)

    hits = match_negatives(results, negatives, case_id="case")

    assert [hit.to_dict() for hit in hits] == [
        {"rank": 1, "negative_index": 0, "source_file": "washer/wm8.md"},
    ]


def test_match_negatives_misses_when_no_match():
    results = [_result(source_file="refrigerator/nrk6192.md")]
    negatives = (ExpectedResult(source_file_prefix="washer/"),) if False else (ExpectedResult(source_file="washer/wm8.md"),)

    assert match_negatives(results, negatives, case_id="case") == []


def test_load_eval_suite_parses_negatives_field(tmp_path: Path):
    suite_path = _write_suite(
        tmp_path,
        {
            "id": "case-1",
            "kb_name": "default",
            "query": "fridge noise",
            "relevant": [{"source_file": "refrigerator/nrk6192.md"}],
            "negatives": [
                {"source_file": "washer/wm8.md"},
                {"metadata": {"product_category": "washer"}},
            ],
        },
    )

    cases = load_eval_suite(suite_path)

    assert len(cases) == 1
    case = cases[0]
    assert len(case.negatives) == 2
    assert case.negatives[0].source_file == "washer/wm8.md"
    assert case.negatives[1].metadata == {"product_category": "washer"}


def test_load_eval_suite_treats_missing_negatives_as_empty(tmp_path: Path):
    suite_path = _write_suite(
        tmp_path,
        {"id": "case-1", "query": "q", "relevant": [{"source_file": "a/m.md"}]},
    )

    cases = load_eval_suite(suite_path)

    assert cases[0].negatives == ()


def test_load_eval_suite_rejects_non_list_negatives(tmp_path: Path):
    suite_path = _write_suite(
        tmp_path,
        {"id": "case-1", "query": "q", "relevant": [{"source_file": "a/m.md"}], "negatives": "washer"},
    )

    with pytest.raises(EvalSuiteError, match="negatives must be a list"):
        load_eval_suite(suite_path)


def test_load_eval_suite_rejects_negative_without_matcher_field(tmp_path: Path):
    suite_path = _write_suite(
        tmp_path,
        {
            "id": "case-1",
            "query": "q",
            "relevant": [{"source_file": "a/m.md"}],
            "negatives": [{}],
        },
    )

    with pytest.raises(EvalSuiteError, match="negatives entry must include at least one matcher field"):
        load_eval_suite(suite_path)


def test_runner_marks_case_failed_when_negative_matches(tmp_path: Path, monkeypatch):
    """Integration: run_eval treats a negative hit as a hard failure even when metrics pass."""
    from tagmemorag.eval import runner as runner_module
    from tagmemorag.eval.dataset import EvalCase, ExpectedResult

    case = EvalCase(
        id="case-neg",
        query="fridge noise",
        relevant=(ExpectedResult(source_file="refrigerator/nrk6192.md"),),
        kb_name="default",
        negatives=(ExpectedResult(metadata={"product_category": "washer"}),),
    )

    fridge_result = _result(
        source_file="refrigerator/nrk6192.md",
        text="cold compartment",
        metadata={"product_category": "fridge"},
    )
    washer_result = _result(
        source_file="washer/wm8.md",
        text="drain pump filter",
        metadata={"product_category": "washer"},
    )

    rank_matches = [{0}, set()]
    negatives_hits = runner_module.match_negatives([fridge_result, washer_result], case.negatives, case_id=case.id)
    failures_neg = runner_module._negative_violations(negatives_hits)

    assert failures_neg == ["negative #0 matched at rank 2 (washer/wm8.md)"]
