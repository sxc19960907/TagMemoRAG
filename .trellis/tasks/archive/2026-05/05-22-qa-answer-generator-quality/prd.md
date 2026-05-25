# QA answer generator quality

## Goal

Improve the deterministic offline QA answer generator so product-manual answers are clearer, safer, and less likely to overclaim when the retrieved evidence is incomplete.

## Requirements

- Keep the noop answer provider deterministic and offline; do not introduce network or model-provider dependencies.
- Preserve the existing citation validation path and exact citation ids from retrieved evidence.
- Use only retrieved evidence when composing answers; do not invent product facts, part numbers, or repair instructions.
- Make product-manual answers more useful for users by formatting multi-step troubleshooting and maintenance guidance clearly.
- Prioritize safety guidance when evidence mentions danger signals such as abnormal smell, leakage, electric shock risk, overheating, or instructions to disconnect power and contact support.
- Refuse or mark insufficient evidence for unsupported replacement, disassembly, or part-number questions when retrieved evidence does not support a definite answer.
- Verify the change with unit tests, the answer-quality suite, and real product manuals from `product_manuals/`.

## Acceptance Criteria

- [ ] Unit tests cover stepwise product-manual formatting, safety prioritization, unsupported replacement/part-number refusal, and no fabricated citations.
- [ ] Existing focused answer/API regression tests pass.
- [ ] `uv run python -m tagmemorag eval answer-quality --suite tests/fixtures/answer_quality/qa_product_manual.jsonl` passes.
- [ ] A real product manual verification against `product_manuals/` is run and the result is recorded in the final report.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
