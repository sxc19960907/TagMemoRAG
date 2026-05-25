# General-web ranking pressure diagnostic

## Goal

Add a reusable diagnostic report for general-web retrieval ranking pressure so
future ranking work can start from reproducible evidence instead of ad hoc
inspection.

The current release-readiness baseline is passed. The remaining useful
optimization target is not a release blocker: GitHub Hello World general-web
cases still show definition-style evidence ranked below broad tutorial
overview/action chunks. This task should make those ranking-pressure cases
visible without changing runtime retrieval behavior.

## Confirmed Facts

- The active direction is general-purpose RAG.
- Current release-readiness status is passed after the MDN eval-label correction.
- GitHub Hello World repository/pull-request cases remain future ranking pressure.
- Prior diagnostics found no safe broad scoring signal:
  `lexical_evidence_score` can prefer overview/action chunks over expected
  definition chunks.
- Existing `scripts/summarize_eval_case_review.py` summarizes eval reports but
  does not classify ranking pressure or compare matched versus pre-match ranks.

## Requirements

- Add a diagnostic script or extend an existing one to read a retained eval JSON
  report and emit a bounded JSON/Markdown ranking-pressure report.
- The report must identify cases with:
  - hit@k present
  - recall above zero
  - MRR below `1.0`
  - first matched expected result not at rank 1
- For each case, include bounded metadata:
  - case id, kb name, metrics
  - first matched rank
  - expected count and matched indexes
  - short per-rank feature summaries for top results before/at first match
  - cue counts for definition, overview, action/workflow, and source/page chrome
  - whether a rank matched expected evidence
- Do not include raw query text by default.
- Do not include raw result snippets, full source paths beyond existing
  `source_file`, vectors, secrets, or `.tmp` report bodies in committed files.
- Do not change retrieval/ranking/parser/context/answer behavior.
- Leave unrelated `.codegraph/` and `.mcp.json` untouched.

## Acceptance Criteria

- [ ] The diagnostic produces a JSON report for the current general-web eval
      report and highlights the GitHub ranking-pressure cases.
- [ ] Markdown rendering is available for human review.
- [ ] Unit tests cover ranking-pressure classification, privacy defaults, and
      CLI output.
- [ ] Existing eval review tests still pass.
- [ ] No runtime retrieval behavior or eval fixtures are changed.

## Notes

- This is a diagnostic/tooling task, not an optimization task.
