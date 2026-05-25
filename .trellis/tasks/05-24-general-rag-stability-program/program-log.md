# Program Log

## 2026-05-24 Kickoff

User asked for a long-running task: make a plan, keep executing based on each
task's results, and preserve system stability.

Current baseline:

- Release readiness: `passed`
- General-web retrieval: `hit@k=1.0`, `recall_at_k=0.971429`, `MRR=0.773810`
- Ranking pressure: `2` cases, highest pressure ranks `5`
- Reranking evaluation gate exists and is documented.

Decision:

- Create this parent program and keep it active.
- First child: baseline batch self-check.
- No runtime ranking change until gates prove a candidate is safe.

## 2026-05-24 Child 1: Baseline Batch Self-Check

Child task: `05-24-baseline-batch-self-check`

Result:

- Focused tests: `22 passed`
- Release readiness: `passed`
- General-web retrieval: `hit@k=1.0`, `recall_at_k=0.971429`, `MRR=0.773810`
- Ranking pressure: `2` cases, highest pressure ranks `5`
- Reranking gate self-check: `passed`, failed checks `[]`

Classification: `ship`

Decision:

- Baseline is stable enough to continue.
- Next child should automate the self-check into a batch runner, so future
  candidate tasks use one repeatable command instead of manual command stitching.

## 2026-05-24 Child 2: Gate Batch Runner

Child task: `05-24-gate-batch-runner`

Result:

- Added `src/tagmemorag/reranking_gate_batch.py`
- Added `scripts/reranking_gate_batch.py`
- Added focused unit coverage for passing/failing batch outcomes and CLI exit
  behavior.
- Focused tests: `21 passed`
- CLI self-check: `passed`
- Release readiness status from batch: `passed`
- Reranking gate status from batch: `passed`
- Failed checks: `[]`

Classification: `ship`

Decision:

- The program now has one repeatable offline command for the current stability
  baseline.
- Next child should be an observational evidence-usefulness dry run that emits a
  bounded report without changing retrieval order.

## 2026-05-24 Child 3: Evidence Usefulness Dry Run

Child task: `05-24-evidence-usefulness-dry-run`

Result:

- Added `src/tagmemorag/evidence_usefulness_diagnostic.py`.
- Added `scripts/diag_evidence_usefulness.py`.
- Added focused unit coverage for summary calculations, privacy omissions,
  Markdown rendering, and CLI invalid input handling.
- Focused tests: `26 passed`.
- Local dry run on `.tmp/eval/general-web-after-evidence-refinement.json`:
  - cases: `7`
  - matched cases: `7`
  - average matched usefulness: `0.568571`
  - average pre-match usefulness: `0.123810`
  - matched beats pre-match count: `7`
  - useful evidence under-ranked count: `0`
- Privacy keyword scan over generated JSON/Markdown found no forbidden raw
  payload markers checked by this task.
- Batch gate after the dry run: `passed`, release readiness `passed`,
  reranking gate `passed`, failed checks `[]`.

Classification: `ship`

Decision:

- Do not convert the usefulness score into runtime ranking weight yet. The
  general-web pressure cases show matched evidence has stronger usefulness
  cues than earlier unmatched ranks, so a naive usefulness boost would be an
  under-evidenced production change.
- Next child should diagnose same-page multi-evidence ordering for the two
  GitHub Hello World low-MRR cases. Focus on rank-local features, duplicate
  page/header effects, and expected-label alignment before proposing any
  scoring candidate.

## 2026-05-24 Child 4: GitHub Same-Page Ordering Diagnostic

Child task: `05-24-github-same-page-ordering-diagnostic`

Result:

- Added `src/tagmemorag/same_page_ordering_diagnostic.py`.
- Added `scripts/diag_same_page_ordering.py`.
- Added focused unit coverage for repeated source/header detection, score-gap
  summaries, near-tie summaries, privacy omissions, Markdown rendering, and
  invalid input handling.
- Focused tests: `33 passed`.
- Local dry run on `.tmp/eval/general-web-after-evidence-refinement.json`:
  - same-page pressure count: `2`
  - same-page not-usefulness count: `2`
  - highest pressure rank count: `5`
  - average top-to-first-match score gap: `0.309000`
  - near-tie case count: `0`
  - `github-hello-world-repository`: first matched rank `6`, pressure ranks
    `5`, repeated source/header `8/8`, score gap `0.436000`
  - `github-hello-world-pull-request`: first matched rank `4`, pressure ranks
    `3`, repeated source/header `8/8`, score gap `0.182000`
- Privacy keyword scan over generated JSON/Markdown found no forbidden raw
  payload markers checked by this task.
- Batch gate after the dry run: `passed`, release readiness `passed`,
  reranking gate `passed`, failed checks `[]`.

Classification: `ship`

Decision:

- The remaining general-web ranking pressure is concentrated in same-page,
  same-header GitHub results where matched evidence is useful but lower-scored.
- Next child may design a bounded candidate for same-source/header diversity or
  same-page representative ordering. The candidate must remain default-off or
  diagnostic-only until it passes baseline, candidate, and release-readiness
  gates without degrading non-GitHub slices.

## 2026-05-24 Child 5: Same-Page Ordering Candidate Dry Run

Child task: `05-24-same-page-ordering-candidate-dry-run`

Result:

- Added `src/tagmemorag/same_page_ordering_candidate.py`.
- Added `scripts/diag_same_page_candidate.py`.
- Added focused unit coverage for improvement, no-op behavior, pressure-case
  regression detection, rank-1 safety, privacy omissions, Markdown rendering,
  candidate ranking-pressure output, and CLI invalid input handling.
- Focused tests: `36 passed`.
- Local dry run on `.tmp/eval/general-web-after-evidence-refinement.json`:
  - candidate status: `passed`
  - changed cases: `2`
  - improved cases: `2`
  - regressed cases: `0`
  - baseline MRR: `0.773810`
  - candidate MRR: `1.000000`
  - baseline ranking pressure count: `2`
  - candidate ranking pressure count: `0`
  - baseline highest pressure rank count: `5`
  - candidate highest pressure rank count: `0`
  - `github-hello-world-repository`: first matched rank `6` -> `1`
  - `github-hello-world-pull-request`: first matched rank `4` -> `1`
- Privacy keyword scan over generated JSON/Markdown found no forbidden raw
  payload markers checked by this task.
- Batch gate with candidate ranking-pressure report: `passed`, release
  readiness `passed`, reranking gate `passed`, failed checks `[]`.

Classification: `ship`

Decision:

- A pressure-gated same-page candidate is promising: it only reorders cases
  whose baseline first match is below rank 1, preserving existing rank-1 hits
  in the retained report.
- Next child may design a guarded runtime implementation behind a default-off
  setting or diagnostic flag. It must reuse the dry-run gate as the acceptance
  baseline and run broader non-GitHub slices before any default-on proposal.

## 2026-05-24 Child 6: Same-Page Ordering Runtime Flag

Child task: `05-24-same-page-ordering-runtime-flag`

Result:

- Added `src/tagmemorag/same_page_ordering.py` with a pure deterministic
  pressure-gated same-page ordering helper.
- Added `search.same_page_ordering_enabled`, default `false`.
- Added `search.same_page_ordering_min_group_size`, default `2`.
- Wired `build_retrieve_response` and `/retrieve` to pass the option from
  settings while preserving default-off behavior.
- Added config tests for defaults, env overrides, and YAML overrides.
- Added retrieval tests proving:
  - disabled flag preserves result/evidence order
  - enabled flag promotes the same-page pressure result
  - enabled flag preserves rank-1 useful results
- Focused adjacent tests: `106 passed`.
- Batch gate after runtime wiring: `passed`, release readiness `passed`,
  reranking gate `passed`, failed checks `[]`.

Classification: `ship`

Decision:

- The runtime code path is present but default-off, so baseline release behavior
  remains unchanged.
- Next child should run explicit eval with `same_page_ordering_enabled=true`
  against the retained/general-web slice and at least one broader non-GitHub
  slice before considering any default-on proposal.

## 2026-05-25 Child 7: Same-Page Ordering Explicit Eval

Child task: `05-25-same-page-ordering-explicit-eval`

Result:

- Wired `tagmemorag eval run` to honor `search.same_page_ordering_enabled`.
- Added eval-runner tests proving default-off behavior is unchanged and
  enabled behavior can promote a same-page pressure fixture.
- Hardened `reranking_eval_gate` so candidate reports fail if they introduce a
  new ranking-pressure case id, even when aggregate pressure count does not
  increase.
- Refined runtime same-page ordering to preserve rank-1 results whose bounded
  usefulness is already sufficient.
- Focused adjacent tests: `103 passed`.
- Explicit general-web eval with `same_page_ordering_enabled=true`:
  - cases: `7`
  - hit@k: `1.000000`
  - recall@k: `0.971429`
  - MRR: `1.000000`
  - ranking pressure count: `0`
  - highest pressure rank count: `0`
- Reranking gate with explicit candidate pressure report: `passed`, failed
  checks `[]`.
- Mixed-domain guard with the flag enabled:
  - cases: `4`
  - hit@k: `1.000000`
  - recall@k: `1.000000`
  - MRR: `1.000000`
- Privacy keyword scan over generated bounded reports found no forbidden raw
  payload markers checked by this task.

Classification: `ship`

Decision:

- The same-page ordering flag is now validated through both unit tests and
  explicit eval with retained local corpora.
- Keep the flag default-off for now. Next child should either expand guard
  coverage to realmanuals/multiformat if local artifacts are present, or add a
  release-readiness candidate override that can include same-page enabled
  reports without manual command stitching.

## 2026-05-25 Child 8: Candidate-Aware Reranking Gate Batch

Child task: `05-25-05-25-candidate-aware-reranking-gate-batch`

Result:

- Moved the general-web ranking-pressure diagnostic into
  `src/tagmemorag/general_web_ranking_pressure.py`.
- Kept `scripts/diag_general_web_ranking_pressure.py` as a thin CLI wrapper.
- Added `--candidate-eval-report` to the reranking gate batch so a candidate
  eval output can derive `<output-dir>/candidate-ranking-pressure.json`
  automatically.
- Preserved explicit `--candidate-ranking-pressure` precedence for existing
  scripted callers.
- Added focused coverage for derived candidate pressure, explicit pressure
  precedence, CLI wiring, and privacy omissions.
- Focused tests:
  `tests/unit/test_diag_general_web_ranking_pressure.py`,
  `tests/unit/test_reranking_gate_batch.py`, and
  `tests/unit/test_reranking_eval_gate.py`: `24 passed`.
- Local batch run with `.tmp/eval/same-page-enabled-general-web.json` through
  `--candidate-eval-report`: `passed`, release readiness `passed`, reranking
  gate `passed`, failed checks `[]`.
- Privacy keyword scan over generated batch artifacts found no forbidden raw
  payload markers checked by this task.

Classification: `ship`

Decision:

- Future same-page or retrieval-ranking candidates can now run the batch gate
  from an eval report without a manual intermediate diagnostic command.
- Keep the same-page ordering flag default-off. Next child should expand the
  enabled-flag guard coverage to any retained multiformat/realmanuals artifacts
  that are locally available, then decide whether a default-on proposal is
  warranted.
