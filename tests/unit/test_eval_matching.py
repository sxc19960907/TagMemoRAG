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


def test_match_expectations_normalizes_whitespace_for_text_contains():
    result = _result(
        header="Installation",
        text="Leave at\nleast\t50mm   of space behind the appliance.",
    )
    expected = (ExpectedResult(header="Installation", text_contains=("at least 50mm of space",)),)

    assert match_expectations([result], expected, case_id="case-1") == [{0}]


def test_match_expectations_normalizes_control_characters_for_text_contains():
    result = _result(header="Maintenance", text="Clean the pump\u000cfilter every month.")
    expected = (ExpectedResult(header="Maintenance", text_contains=("pump filter",)),)

    assert match_expectations([result], expected, case_id="case-1") == [{0}]


def test_match_expectations_basename_fallback_requires_unique_candidate():
    results = [
        _result(source_file="a/manual.md", text="a"),
        _result(source_file="b/manual.md", text="b"),
    ]
    expected = (ExpectedResult(source_file="manual.md"),)

    with pytest.raises(EvalSuiteError, match="ambiguous"):
        match_expectations(results, expected, case_id="case-1")


def test_match_expectations_supports_metadata_fields():
    result = _result(
        text="冷藏室温度可以调节。",
        metadata={"manual_id": "fridge-manual", "product_category": "fridge", "tags": ["temperature-setting"]},
    )
    expected = (ExpectedResult(metadata={"manual_id": "fridge-manual", "tags": ["temperature-setting"]}),)
    missing = (ExpectedResult(metadata={"manual_id": "fridge-manual", "tags": ["maintenance"]}),)

    assert match_expectations([result], expected, case_id="case-1") == [{0}]
    assert match_expectations([result], missing, case_id="case-1") == [set()]


def _result(
    *,
    source_file: str = "coffee.md",
    header: str = "h",
    text: str = "text",
    anchor_key: str = "anchor",
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
