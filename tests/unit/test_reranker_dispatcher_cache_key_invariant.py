from __future__ import annotations

from dataclasses import dataclass

from tagmemorag.config import Settings
from tagmemorag.queryplan import build_plan
from tagmemorag.reranker import RerankerDispatcher


@dataclass
class _Candidate:
    chunk_id: str
    text: str = ""


class _Primary:
    id = "fake@test"
    version = "v1"
    max_seq_length = 512
    supports_instruction = True


def test_cache_key_depends_on_candidate_set_not_agent_step_idx():
    # Parent D6 + C1 R10: RerankerDispatcher cache keys are plan/candidate
    # scoped. Agent step index must stay outside this function so classic
    # rerank caching remains byte-equivalent and reusable across agent steps.
    dispatcher = RerankerDispatcher(Settings(), primary=_Primary())
    plan = build_plan("washer drain", "kb", Settings())
    candidates_a = [_Candidate("c1"), _Candidate("c2")]
    candidates_b = [_Candidate("c1"), _Candidate("c3")]

    assert dispatcher._cache_key(plan, candidates_a) == dispatcher._cache_key(plan, list(reversed(candidates_a)))
    assert dispatcher._cache_key(plan, candidates_a) != dispatcher._cache_key(plan, candidates_b)
