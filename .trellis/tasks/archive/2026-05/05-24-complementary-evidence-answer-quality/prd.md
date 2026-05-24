# Validate Complementary Evidence Answers

## Problem

Context packing now prefers complementary evidence under tight token budgets, but the previous validation stopped mostly at retrieval/context-pack shape. We need an answer-quality check that proves the final local answer can cite multiple complementary evidence points when budget pressure exists.

## Goals

- Add a deterministic answer-quality regression for a tight-budget multi-evidence public-doc question.
- Reuse existing retrieval and noop answer-generation diagnostics.
- Keep validation offline and local; do not introduce an LLM judge.
- Preserve bounded reports without raw provider output or secrets.

## Non-Goals

- Do not change answer schemas.
- Do not add provider-specific behavior.
- Do not change retrieval ranking in this task.

## Acceptance Criteria

- A unit/integration diagnostic proves the GitHub repository/README answer includes both repository/folder and README/Markdown citations when run with a tight context budget.
- Existing answer-quality, answer-generator, and retrieval tests pass.
- The seeded general-web answer diagnostic remains green.

