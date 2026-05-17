"""Unit tests for scripts/diag_realmanuals_eval.py helpers (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import diag_realmanuals_eval as dre  # noqa: E402

from tagmemorag.eval.dataset import EvalCase, ExpectedResult  # noqa: E402
from tagmemorag.types import Result  # noqa: E402


def _case(case_id: str, tags: tuple[str, ...]) -> EvalCase:
    return EvalCase(
        id=case_id,
        query="q",
        tags=tags,
        relevant=(ExpectedResult(text_contains=("placeholder",)),),
    )


def _result(category: str, source_file: str = "") -> Result:
    return Result(
        node_id=1,
        score=0.5,
        text="body",
        header="Page 1",
        path=[],
        source_file=source_file,
        start_line=0,
        anchor_key="a",
        product_category=category,
        metadata={"product_category": category},
    )


def test_product_tag_uses_first_known_product_tag():
    assert dre._product_tag(_case("c", ("fault", "washer"))) == "washer"


def test_product_tag_rejects_cases_without_product_category():
    with pytest.raises(ValueError):
        dre._product_tag(_case("c", ("fault", "operation")))


def test_category_falls_back_to_source_file_prefix():
    result = _result("", source_file="dryer/HISENSE DHGA901NL.pdf")

    assert dre._category(result) == "dryer"


def test_reciprocal_rank_returns_first_matching_rank():
    assert dre._reciprocal_rank(("refrigerator", "washer", "washer"), "washer") == 0.5
    assert dre._reciprocal_rank(("refrigerator",), "washer") == 0.0


def test_aggregate_computes_category_hit_metrics():
    items = [
        dre.CaseDiag("a", "q", "washer", ("washer", "dryer"), ("w.pdf", "d.pdf"), 1.0),
        dre.CaseDiag("b", "q", "dryer", ("washer", "dryer"), ("w.pdf", "d.pdf"), 0.5),
        dre.CaseDiag("c", "q", "oven", ("washer", "dryer"), ("w.pdf", "d.pdf"), 0.0),
    ]

    metrics = dre._aggregate(items)

    assert metrics["top1_category_hit"] == pytest.approx(1 / 3)
    assert metrics["top3_category_hit"] == pytest.approx(2 / 3)
    assert metrics["top5_category_hit"] == pytest.approx(2 / 3)
    assert metrics["mean_reciprocal_category_rank"] == pytest.approx(0.5)


def test_format_report_includes_core_delta_sections():
    results = {
        "vec-only": [
            dre.CaseDiag("a", "q", "washer", ("dryer", "washer"), ("d.pdf", "w.pdf"), 0.5),
        ],
        "wave-baseline": [
            dre.CaseDiag("a", "q", "washer", ("washer", "dryer"), ("w.pdf", "d.pdf"), 1.0),
        ],
    }

    report = dre._format_report(
        results,
        meta={"chunk_count": 2, "model_name": "m", "model_dim": 4},
        top_k=5,
        parser_stats=[
            {
                "source_file": "dryer/manual.pdf",
                "chunks": 4,
                "detected": 3,
                "fallback": 1,
                "sample_headers": ["Safety", "Operation"],
            }
        ],
    )

    assert "Real Manuals PDF Routing Diagnostic" in report
    assert "PDF parser structure stats" in report
    assert "Delta: wave-baseline - vec-only" in report
    assert "top1_category_hit: +1.000" in report
    assert "a:" in report
