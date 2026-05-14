from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePath

from tagmemorag.types import Result

from .dataset import EvalSuiteError, ExpectedResult


@dataclass(frozen=True)
class NegativeHit:
    rank: int
    negative_index: int
    source_file: str

    def to_dict(self) -> dict[str, int | str]:
        return {"rank": self.rank, "negative_index": self.negative_index, "source_file": self.source_file}


def match_expectations(
    results: list[Result],
    expected: tuple[ExpectedResult, ...],
    *,
    case_id: str,
) -> list[set[int]]:
    source_index = _source_index(results)
    matches: list[set[int]] = []
    for result in results:
        matched: set[int] = set()
        for index, expectation in enumerate(expected):
            if _matches(result, expectation, source_index, case_id, index):
                matched.add(index)
        matches.append(matched)
    return matches


def match_negatives(
    results: list[Result],
    negatives: tuple[ExpectedResult, ...],
    *,
    case_id: str,
) -> list[NegativeHit]:
    if not negatives:
        return []
    source_index = _source_index(results)
    hits: list[NegativeHit] = []
    for rank, result in enumerate(results, start=1):
        for negative_index, negative in enumerate(negatives):
            if _matches(result, negative, source_index, case_id, negative_index):
                hits.append(NegativeHit(rank=rank, negative_index=negative_index, source_file=result.source_file))
    return hits


def _matches(
    result: Result,
    expectation: ExpectedResult,
    source_index: dict[str, set[str]],
    case_id: str,
    expectation_index: int,
) -> bool:
    if expectation.source_file and not _source_matches(result.source_file, expectation.source_file, source_index, case_id, expectation, expectation_index):
        return False
    if expectation.header and result.header.strip() != expectation.header.strip():
        return False
    if expectation.anchor_key and result.anchor_key != expectation.anchor_key:
        return False
    for needle in expectation.text_contains:
        if needle not in result.text:
            return False
    if expectation.metadata and not _metadata_matches(result.metadata, expectation.metadata):
        return False
    return True


def _metadata_matches(actual: dict, expected: dict) -> bool:
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if isinstance(expected_value, list):
            if not isinstance(actual_value, list):
                return False
            if not all(item in actual_value for item in expected_value):
                return False
        elif actual_value != expected_value:
            return False
    return True


def _source_matches(
    actual: str,
    expected: str,
    source_index: dict[str, set[str]],
    case_id: str,
    expectation: ExpectedResult,
    expectation_index: int,
) -> bool:
    if actual == expected:
        return True
    if "/" in expected or "\\" in expected:
        return False
    candidates = source_index.get(expected, set())
    if len(candidates) > 1:
        expected_id = expectation.id or f"{case_id}#{expectation_index + 1}"
        raise EvalSuiteError(
            f"case {case_id} expected {expected_id} source_file basename {expected!r} is ambiguous: {sorted(candidates)}"
        )
    return len(candidates) == 1 and actual in candidates


def _source_index(results: list[Result]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for result in results:
        index[PurePath(result.source_file).name].add(result.source_file)
    return dict(index)
