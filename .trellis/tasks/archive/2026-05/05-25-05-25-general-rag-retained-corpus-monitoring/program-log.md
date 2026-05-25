# Program Log

## 2026-05-25 Kickoff

The previous general RAG stability program completed same-page ordering
default-on rollout with gates passing and config rollback preserved.

Current baseline:

- `search.same_page_ordering_enabled=true`
- `search.same_page_ordering_min_group_size=2`
- Default-on general-web eval: cases `7`, recall@k `0.971429`, MRR
  `1.000000`, hit@k `1.000000`
- Candidate-aware gate batch: `passed`
- Release readiness: `passed`
- Reranking gate: `passed`
- Failed checks: `[]`

Decision:

- Create this parent program to keep the next phase stable and evidence-led.
- First child: retained corpus inventory.
- Do not make more ranking/retrieval behavior changes until retained coverage
  gaps are known.

## 2026-05-25 Child 1: Retained Corpus Inventory

Child task: `05-25-05-25-retained-corpus-inventory`

Result:

- Inventoried committed eval suites under `tests/fixtures/eval/`.
- Inventoried reusable local corpus locations without committing local corpus
  bodies.
- Recorded key retained default-on and same-page enabled aggregate reports.
- Confirmed latest default-on gate outputs remain available under
  `.tmp/eval/default-on-implementation-gate/`.
- Identified that core post-default-on monitoring slices exist but are small:
  general-web `7`, mixed-domain `4`, multiformat `3`, realmanuals `10`.
- Identified that monitoring is still manually assembled from report paths.

Classification: `ship`

Decision:

- Next child should create a default-on retained monitoring manifest and batch
  summary before adding more corpus cases.
- Do not change retrieval/ranking behavior until a repeatable monitoring
  manifest exists.

## 2026-05-25 Child 2: Default-On Retained Monitoring Manifest

Child task: `05-25-05-25-default-on-retained-monitoring-manifest`

Result:

- Added `examples/default-on-retained-monitoring.json` with the current
  post-default-on retained slices and gate report paths.
- Added `src/tagmemorag/default_on_retained_monitoring.py` to read the manifest
  and summarize existing bounded reports.
- Added `scripts/default_on_retained_monitoring.py` as a thin CLI wrapper.
- Added focused coverage for passing summaries, missing reports, threshold
  regressions, gate regressions, Markdown output, CLI output, and privacy
  omissions.
- Focused tests: `6 passed`.
- Related gate tests: `31 passed`.
- CLI smoke wrote `.tmp/eval/default-on-retained-monitoring-summary.json` with
  status `passed` and failed checks `[]`.
- Real retained summary covered general-web `7`, mixed-domain `4`,
  multiformat `3`, and realmanuals `10` cases.

Classification: `ship`

Decision:

- The program now has a repeatable manifest-driven summary for current
  default-on retained reports.
- Next child should either wire this summary into a command that can rerun the
  listed eval slices, or expand the smallest retained slice. Prefer rerun
  automation first so new cases immediately enter the monitoring loop.

## 2026-05-25 Child 3: Manifest-Driven Retained Monitoring Rerun

Child task: `05-25-05-25-manifest-retained-monitoring-rerun`

Result:

- Extended `run_default_on_retained_monitoring` with optional `rerun=True`.
- Added `scripts/default_on_retained_monitoring.py --rerun`.
- Rerun execution is explicit, parses manifest commands as argument lists,
  and does not persist command stdout/stderr into monitoring reports.
- Summary-only behavior remains unchanged by default.
- Added focused coverage for successful rerun, failed rerun, CLI rerun, and
  unchanged summary-only behavior.
- Focused tests: `9 passed`.
- Related gate tests: `34 passed`.
- Summary-only CLI smoke remained `passed`.

Classification: `ship`

Decision:

- The monitoring path can now summarize retained reports and explicitly rerun
  manifest-declared diagnostics.
- Next child should run the manifest rerun path against the current local
  retained assets, then decide whether to expand mixed-domain or multiformat
  first.
