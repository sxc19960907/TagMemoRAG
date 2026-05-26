# Eval Run Browser Launcher Design

## Scope

This task adds a browser launcher for safe predefined eval runs. It does not add arbitrary suite upload, custom docs roots, live-provider evaluation controls, or a persistent job database.

## Backend Contract

Create a narrow service module `api_eval_runs.py` owned by the API layer. It wraps existing `eval.runner.run_eval` instead of reimplementing retrieval or scoring.

### Suite Whitelist

Define `EVAL_BROWSER_SUITES` as project-local suite definitions. The first version includes one fast, deterministic smoke suite:

- `coffee_smoke`
  - suite: `tests/fixtures/eval/coffee.jsonl`
  - docs: `tests/fixtures`
  - config: current in-memory `settings`
  - thresholds: permissive browser-smoke thresholds matching the stable CLI fixture path (`min_* = 0`) unless a baseline is added later.

The API resolves paths against `Path.cwd()` and rejects definitions escaping the project root.

### Job Registry

Use an in-memory dict plus lock, similar in spirit to rebuild task tracking. Each job carries:

- `job_id`
- `suite_id`
- `status`: queued/running/passed/failed/error
- `created_at`, `started_at`, `finished_at`
- `report_path`
- `summary` when available
- bounded `error` when eval cannot run

A `ThreadPoolExecutor(max_workers=1)` is sufficient for the first version. Reject launching a new eval while another queued/running eval exists to protect local resources.

### API Routes

- `GET /eval/suites`: admin, rate-limited, returns launchable suite definitions.
- `POST /eval/runs`: admin, rate-limited, JSON body `{suite_id}`.
- `GET /eval/runs/{job_id}`: admin, rate-limited, returns job state.

All known errors use `ServiceError` with structured response shape.

### Report Output

Reports write to `.tmp/eval/browser-runs/{timestamp}-{job_id}-{suite_id}.json`. The path is project-local and can be opened by the existing `/admin/eval-report?report_path=...` viewer.

## Frontend Contract

Extend `eval_report.html/js/css` with an Eval Run panel above Recent Reports:

- suite selector
- run button
- current job status strip/card
- Open Report link after success

The page polls the job endpoint until a terminal state. It keeps the existing Recent Reports and explicit path loading behavior.

## Safety and Compatibility

- No shell execution.
- No user-provided filesystem paths for browser-launched evals.
- CLI eval remains unchanged.
- Generated reports use the existing eval report JSON schema.
