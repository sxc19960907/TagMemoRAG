# Represent Multi-Evidence Eval Cases

## Problem

The mixed-domain GitHub case asks for repository, README, Markdown, project, and folder evidence. In the seeded GitHub document, that answer is naturally supported by multiple useful chunks. The general-web suite already models this with two expected evidence entries, but the mixed-domain suite only listed the repository/folder chunk. That makes the mixed report look like a ranking problem even when the top result is a useful README/Markdown chunk.

## Goals

- Align the mixed-domain GitHub case with the existing general-web multi-evidence fixture.
- Keep the eval schema unchanged unless a real limitation appears.
- Preserve wrong-domain negatives and shared-KB behavior.
- Re-run mixed-domain and general-web diagnostics to confirm the report now reflects answer-support quality more accurately.

## Non-Goals

- Do not change retrieval ranking in this task.
- Do not add a new eval metric or schema field unless fixture alignment is insufficient.
- Do not relax thresholds broadly.

## Acceptance Criteria

- `tests/fixtures/eval/mixed_knowledge.jsonl` treats the GitHub README/Markdown evidence as relevant for the mixed GitHub query.
- Mixed-domain report improves for the GitHub case without hiding wrong-domain negatives.
- Existing eval dataset/matching tests remain green.
- Architecture docs mention that multi-evidence questions should list all acceptable supporting evidence chunks.

