from __future__ import annotations

import pytest

from tagmemorag.eval.dataset import EvalSuiteError, ExpectedResult
from tagmemorag.eval.matching import match_expectations
from tagmemorag.types import Result


def test_match_expectations_requires_all_specified_fields():
    result = _result(source_file="docs/coffee.md", header="蒸汽功能", text="若蒸汽很小，检查喷嘴。")
    expected = (ExpectedResult(source_file="coffee.md", header="蒸汽功能", text_contains=("喷嘴",)),)

    assert match_expectations([result], expected, case_id="case-1") == [{0}]


def test_match_expectations_rejects_missing_text_contains():
    result = _result(header="蒸汽功能", text="检查水箱。")
    expected = (ExpectedResult(header="蒸汽功能", text_contains=("喷嘴",)),)

    assert match_expectations([result], expected, case_id="case-1") == [set()]


def test_match_expectations_basename_fallback_requires_unique_candidate():
    results = [
        _result(source_file="a/manual.md", text="a"),
        _result(source_file="b/manual.md", text="b"),
    ]
    expected = (ExpectedResult(source_file="manual.md"),)

    with pytest.raises(EvalSuiteError, match="ambiguous"):
        match_expectations(results, expected, case_id="case-1")


def _result(
    *,
    source_file: str = "coffee.md",
    header: str = "h",
    text: str = "text",
    anchor_key: str = "anchor",
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
    )
