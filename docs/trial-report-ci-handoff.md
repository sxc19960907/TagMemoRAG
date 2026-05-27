# Trial Report And CI Handoff

Use this handoff after a local browser-first trial pass and before treating GitHub CI as the merge signal.

## Retained Local Trial Evidence

Keep one local pilot report for each trial handoff:

```bash
uv run python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/trial-ops-pilot \
  --include-browser-qa \
  --output .tmp/trial-ops-pilot/report.json
```

Retain these paths locally or attach them to the external rollout record:

- `.tmp/trial-ops-pilot/report.json`
- `.tmp/trial-ops-pilot/readiness/`
- any eval report linked from the `browser_qa_readiness` or Retrieval Quality flow

Do not commit `.tmp/` reports. They are operator evidence, not source artifacts.

## When To Use Full Browser QA

Use the focused browser stage for ordinary trial evidence. Add `--browser-qa-full` when broad browser/admin flows changed:

```bash
uv run python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/trial-ops-pilot \
  --include-browser-qa \
  --browser-qa-full \
  --output .tmp/trial-ops-pilot/report.json
```

## GitHub CI Boundary

`.github/workflows/quality.yml` runs on pull requests and pushes to `master` or `main`.

Default CI currently runs:

- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
- `uv run python scripts/run_eval_ci.py`

Default CI does not run `readiness browser-qa` or `pilot run --include-browser-qa`. Those browser checks remain local opt-in because they start a server and Playwright browser flow. Treat the retained local pilot report as browser-trial evidence, then treat GitHub CI as authoritative once changes are pushed.

## Handoff Checklist

- Local pilot report exists at `.tmp/trial-ops-pilot/report.json`.
- Report status is `passed`, or warnings are explicitly accepted by the trial owner.
- `browser_qa_readiness` is present and `passed` when browser evidence is required.
- Retrieval Quality eval drafts have either been run in the browser or retained for follow-up.
- GitHub CI is checked after push; any CI failure overrides local confidence until fixed.
