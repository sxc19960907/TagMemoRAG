# LangChain Loader and Splitter Adapter Spike

## Goal

Evaluate optional LangChain loaders/text splitters behind an adapter while preserving chunk identity, metadata, and eval gates. Planning only until approved.

## Requirements

- Evaluate LangChain document loaders and text splitters behind an optional
  adapter.
- Preserve current chunk identity, metadata, table/page semantics, and parser
  profiles.
- Keep current parser/chunker as default unless eval evidence supports a
  change.

## Acceptance Criteria

- [ ] Optional dependency is isolated behind an extra or adapter boundary.
- [ ] Fixture comparison covers Markdown, TXT, PDF, and at least one new
      loader type if added.
- [ ] `coffee.jsonl` and `product_manuals.jsonl` gates are named before
      implementation.
- [ ] No raw text leakage in logs/debug artifacts.
- [ ] Rollback is deleting the adapter and optional dependency.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
