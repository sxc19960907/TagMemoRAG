# Real manual retrieval quality

## Goal

Improve retrieval quality for real PDF product manuals so `/retrieve`, `/answer`, and `/qa` are more likely to use the correct manual section as evidence.

## Requirements

- Use the real manuals under `product_manuals/` as the primary validation source.
- Diagnose the current `tests/fixtures/eval/realmanuals.jsonl` failures before changing ranking behavior.
- Prefer targeted fixes that improve evidence quality, such as filtering low-value PDF chunks, stronger model/category narrowing, or safer lexical ranking behavior.
- Preserve deterministic offline behavior with the hashing model and local eval commands.
- Do not tune only to one query by hard-coding fixture ids, source files, or case ids.
- Avoid weakening API contracts or changing answer schemas; the main surface is retrieval evidence quality.
- Keep report output and tests bounded; do not commit large eval JSON dumps.

## Acceptance Criteria

- [ ] A failure analysis identifies the main reasons for missed or noisy real-manual cases.
- [ ] At least one retrieval/evidence-quality improvement is implemented with focused tests.
- [ ] `uv run python -m tagmemorag eval run --suite tests/fixtures/eval/realmanuals.jsonl --docs <real-manual-docs> --config examples/config/qa-demo.yaml ...` improves the real-manual summary versus the current baseline (`hit@5=0.4`, `recall@5=0.283333`, `mrr=0.233333`) or documents why the safest first patch targets a narrower metric.
- [ ] Existing focused retrieval, answer, and eval tests pass.
- [ ] Any durable lesson about real PDF parsing/ranking is captured in `.trellis/spec/`.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
