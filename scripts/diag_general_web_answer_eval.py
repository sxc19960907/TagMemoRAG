#!/usr/bin/env python3
"""Run live general-web retrieval through the local answer-quality diagnostic.

The script expects a seeded corpus from `scripts/seed_general_web_eval.sh`.
It intentionally remains opt-in because the corpus is materialized under `.tmp`
from public URLs and is not part of fixture-only CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tagmemorag.answer import create_answer_generator  # noqa: E402
from tagmemorag.answer.base import AnswerRequestContext  # noqa: E402
from tagmemorag.answer.prompt import build_answer_prompt, validate_generation_citations  # noqa: E402
from tagmemorag.config import AnswerConfig, StorageConfig, load_config  # noqa: E402
from tagmemorag.embedder import create_embedder  # noqa: E402
from tagmemorag.eval.answer_quality import (  # noqa: E402
    AnswerQualityCase,
    AnswerQualityContext,
    AnswerQualityExpected,
    evaluate_answer_quality_case,
)
from tagmemorag.eval.dataset import EvalSuiteError, load_eval_suite  # noqa: E402
from tagmemorag.metadata_narrowing import infer_metadata_narrowing, merge_inferred_filters  # noqa: E402
from tagmemorag.retrieval import DEFAULT_TOKEN_BUDGET, build_retrieve_response  # noqa: E402
from tagmemorag.search_runtime import execute_search  # noqa: E402
from tagmemorag.state import build_kb  # noqa: E402


DEFAULT_SUITE = "tests/fixtures/eval/general_web.jsonl"
DEFAULT_DOCS = ".tmp/general-web-eval/general_web"
DEFAULT_CONFIG = "examples/config/local-hashing-npz.yaml"
DEFAULT_KB = "general_web"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--docs", default=DEFAULT_DOCS)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--kb", default=DEFAULT_KB)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--source-k", type=int, default=None)
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    try:
        report = run_diagnostic(
            suite_path=args.suite,
            docs_path=args.docs,
            config_path=args.config,
            kb_name=args.kb,
            top_k=args.top_k,
            source_k=args.source_k,
            token_budget=args.token_budget,
        )
    except EvalSuiteError as exc:
        print(f"general-web answer eval error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - diagnostics should return clean CLI failures.
        print(f"general-web answer eval error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    summary = report["summary"]
    print(
        "general-web answer eval "
        f"{'passed' if summary['passed'] else 'failed'}: "
        f"cases={summary['cases']} failed={summary['failed']}"
    )
    return 0 if summary["passed"] else 1


def run_diagnostic(
    *,
    suite_path: str | Path = DEFAULT_SUITE,
    docs_path: str | Path = DEFAULT_DOCS,
    config_path: str | Path = DEFAULT_CONFIG,
    kb_name: str = DEFAULT_KB,
    top_k: int = 5,
    source_k: int | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> dict:
    cfg = load_config(config_path)
    cfg = cfg.model_copy(deep=True)
    cfg.storage = StorageConfig(data_dir=str(Path(".tmp") / "eval" / uuid4().hex), schema_version=cfg.storage.schema_version)
    cfg.answer = AnswerConfig(enabled=True, provider="noop", model_id="noop")

    cases = [case for case in load_eval_suite(suite_path) if case.kb_name == kb_name]
    if not cases:
        raise EvalSuiteError(f"No eval cases found for kb {kb_name!r}")

    embedder = create_embedder(
        cfg.model.name,
        cfg.model.device,
        cfg.model.batch_size,
        cfg.model.dim,
        provider=cfg.model.provider,
        base_url=cfg.model.base_url,
        embeddings_url=cfg.model.embeddings_url,
        api_key_env=cfg.model.api_key_env,
        timeout_seconds=cfg.model.timeout_seconds,
        dimensions=cfg.model.dimensions,
        normalize=cfg.model.normalize,
    )
    state = build_kb(docs_path, kb_name, cfg, embedder=embedder)
    generator = create_answer_generator(cfg)

    case_reports = []
    for index, case in enumerate(cases, 1):
        answer_payload = _answer_case(
            cfg=cfg,
            state=state,
            embedder=embedder,
            generator=generator,
            case=case,
            top_k=case.top_k_override or top_k,
            source_k=source_k or cfg.search.source_k,
            token_budget=token_budget,
            ordinal=index,
        )
        quality_case = _quality_case_from_answer(case.id, case.query, answer_payload)
        quality = evaluate_answer_quality_case(quality_case)
        case_reports.append(
            {
                "id": case.id,
                "query": case.query,
                "passed": quality.passed,
                "answer": answer_payload["answer"],
                "answer_quality": quality.to_dict(),
                "retrieve": {
                    "evidence_count": len(answer_payload["retrieve"].get("evidence") or []),
                    "context_item_count": len((answer_payload["retrieve"].get("context_pack") or {}).get("items") or []),
                    "answerable": bool((answer_payload["retrieve"].get("answerability") or {}).get("answerable")),
                },
            }
        )
    failed = sum(1 for item in case_reports if not item["passed"])
    return {
        "schema_version": "general_web_answer_eval.v1",
        "suite": str(suite_path),
        "docs": str(docs_path),
        "kb_name": kb_name,
        "summary": {"cases": len(case_reports), "failed": failed, "passed": failed == 0},
        "cases": case_reports,
    }


def _answer_case(*, cfg, state, embedder, generator, case, top_k: int, source_k: int, token_budget: int, ordinal: int) -> dict:
    query_vec = embedder.encode_query(case.query)
    narrowing = infer_metadata_narrowing(
        query_text=case.query,
        graph=state.graph,
        explicit_filters=None,
        enabled=cfg.search.metadata_narrowing_enabled,
        category_policy=cfg.search.metadata_narrowing_category_policy,
        brand_policy=cfg.search.metadata_narrowing_brand_policy,
        min_candidates=cfg.search.metadata_narrowing_min_candidates,
    )
    execution = execute_search(
        state=state,
        query_vec=query_vec,
        settings=cfg,
        query_text=case.query,
        top_k=top_k,
        source_k=source_k,
        steps=cfg.search.steps,
        decay=cfg.search.decay,
        amplitude_cutoff=cfg.search.amplitude_cutoff,
        aggregate=cfg.search.aggregate,
        filters=merge_inferred_filters(None, narrowing),
        boost_filters=narrowing.boost_filters,
    )
    retrieve_payload = build_retrieve_response(
        results=execution.results,
        build_id=state.build_id,
        kb_name=state.kb_name,
        trace_id="diag-general-web-answer",
        search_id=f"diag-search-{ordinal:03d}",
        retrieve_id=f"diag-retrieve-{ordinal:03d}",
        token_budget=token_budget,
        query_text=case.query,
    )
    prompt = build_answer_prompt(question=case.query, retrieve_payload=retrieve_payload, prompt_version=cfg.answer.prompt_version)
    context = AnswerRequestContext(
        question=case.query,
        retrieve_payload=retrieve_payload,
        prompt=prompt,
        max_output_tokens=cfg.answer.max_output_tokens,
    )
    generation = validate_generation_citations(generator.generate(context), prompt.allowed_citation_ids)
    return {
        "answer": generation.to_answer_dict(confidence=float((retrieve_payload.get("answerability") or {}).get("confidence") or 0.0)),
        "retrieve": retrieve_payload,
    }


def _quality_case_from_answer(case_id: str, question: str, answer_payload: dict) -> AnswerQualityCase:
    retrieve = answer_payload["retrieve"]
    answer = answer_payload["answer"]
    contexts = tuple(
        AnswerQualityContext(
            citation_id=str(item.get("citation_id") or ""),
            text=str(item.get("content") or ""),
            source=str((item.get("source") or {}).get("source_file") or ""),
        )
        for item in (retrieve.get("context_pack") or {}).get("items") or []
        if str(item.get("citation_id") or "")
    )
    return AnswerQualityCase(
        id=case_id,
        question=question,
        answer=str(answer.get("text") or ""),
        contexts=contexts,
        expected=AnswerQualityExpected(grounded=True, relevant=True, citation_supported=True),
        notes="generated from live general web retrieval",
    )


if __name__ == "__main__":
    raise SystemExit(main())
