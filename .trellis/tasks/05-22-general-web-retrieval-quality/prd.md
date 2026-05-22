# Improve general web retrieval

## Goal

Make the general web benchmark accurately measure multi-evidence retrieval for
public documentation. The immediate target is the GitHub Hello World repository
case: diagnostics show the system retrieves the repository definition chunk and
the README/Markdown chunk in the top 8, but the eval suite currently models
both snippets as one expected result, which requires a single chunk to contain
both facts.

## Requirements

- Preserve the general web suite as a realistic public-documentation benchmark.
- Fix the GitHub repository case so adjacent, independently relevant chunks are
  represented as separate expected evidence items.
- Keep the suite seeded from real public docs in `.tmp`; do not commit fetched
  public web content.
- Do not hide genuine retrieval failures by lowering thresholds. The suite
  should pass because expected evidence modeling matches retrieved evidence.
- Document the corrected baseline behavior in README.

## Acceptance Criteria

- [ ] `github-hello-world-repository` checks both repository/folder evidence
      and README/Markdown evidence as separate relevant results.
- [ ] The general web suite passes with local hashing thresholds at
      `min-recall-at-k=1.0`, `min-hit-at-k=1.0`, and a realistic MRR threshold.
- [ ] Focused eval tests still pass.
- [ ] No sampled third-party web content is committed.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
