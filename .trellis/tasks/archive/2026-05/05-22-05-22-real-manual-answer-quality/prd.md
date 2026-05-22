# Answer evidence quality for real manuals

## Goal

Improve RAG retrieval and answer quality for real product manuals by tightening the evidence that reaches `/answer` and `/qa/answer`, using the PDFs under `product_manuals/` as the primary validation source.

## Requirements

- Use the real manuals under `product_manuals/` and the fixed `tests/fixtures/eval/realmanuals.jsonl` retrieval slice before changing ranking or answer behavior.
- Diagnose the current remaining miss/noise cases after the prior CJK lexical improvement (`hit@5=0.8`, `recall@5=0.633333`, `mrr=0.516667`) and identify whether the next bottleneck is PDF chunk quality, evidence ranking, or extractive answer filtering.
- Implement one focused, deterministic improvement that makes retrieved evidence or generated extractive answers more relevant for real manuals.
- Preserve public API and answer schemas; `/qa` must remain a user-facing page without debug controls or KB selection.
- Preserve deterministic offline validation with the hashing profile; do not require network LLM calls or LLM-as-judge evaluation.
- Do not hard-code eval case ids, specific source files, node ids, or expected fixture answers into production code.
- Keep diagnostic outputs bounded and do not commit large `.tmp` eval artifacts.

## Acceptance Criteria

- [x] Failure analysis documents the main remaining real-manual retrieval or answer-quality issue being targeted.
- [x] A focused implementation lands with unit or API tests covering the behavior.
- [x] `uv run python -m tagmemorag eval run --suite tests/fixtures/eval/realmanuals.jsonl --docs <real-manual-docs> --config examples/config/qa-demo.yaml ...` is run against real manual PDFs and does not regress the prior realmanuals baseline (`hit@5=0.8`, `recall@5=0.633333`, `mrr=0.516667`), or the task documents why the improvement targets answer quality rather than retrieval metrics.
- [x] `uv run python -m tagmemorag eval answer-quality --suite tests/fixtures/answer_quality/qa_product_manual.jsonl` passes.
- [x] Existing focused retrieval/answer tests pass.
- [x] Any durable lesson about real PDF evidence quality or answer filtering is captured in `.trellis/spec/`.

## Result

The targeted failure mode was table-of-contents and short-heading chunks tying with, or outranking, evidence chunks that contain the actual procedure/explanation text. The implementation keeps identity fields useful for exact model/code matching but stops ordinary topic terms from being rewarded from `source_file`, `manual_id`, category tags, and similar metadata. It also gives specific multi-term heading/body matches more scoring headroom.

Final real-manual retrieval result: `hit@5=1.0`, `recall@5=0.966667`, `mrr=0.691667`, `precision@5=0.32`.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
