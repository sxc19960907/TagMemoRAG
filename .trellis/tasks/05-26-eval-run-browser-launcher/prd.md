# Eval Run Browser Launcher

## Goal

Let an admin run a safe, predefined RAG evaluation from the browser and open the generated report without using the command line.

## Requirements

- Add an admin-only browser/API flow for launching eval runs.
- Only predefined project-local eval suites may be launched from the browser in this task.
- The browser must not accept arbitrary shell commands or arbitrary filesystem roots.
- Eval runs must execute as background jobs with a status endpoint so the page stays responsive.
- Each run must write its JSON report under a bounded project-local `.tmp/eval/browser-runs/` directory.
- Completed jobs must expose the generated report path and a link-compatible report viewer URL.
- Failed jobs must expose a bounded error message without stack traces, document snippets, provider bodies, or secrets.
- Existing CLI eval behavior and report schema must remain compatible.

## Acceptance Criteria

- [ ] `GET /eval/suites` returns a small whitelist of launchable eval suites with name, suite path, docs path, and default thresholds.
- [ ] `POST /eval/runs` starts one background eval job for a selected suite and returns `202` with a job id.
- [ ] `GET /eval/runs/{job_id}` returns status, timestamps, selected suite metadata, report path when complete, and bounded errors when failed.
- [ ] Duplicate/invalid suite ids return structured `INVALID_REQUEST` errors and do not launch a job.
- [ ] Eval Report page includes a launch panel, can start a run, polls status, and offers an Open Report action on success.
- [ ] Browser smoke covers launching a lightweight fixture eval and opening its report.
- [ ] Unit tests cover suite listing, invalid suite rejection, job success/failure shape, and page/static wiring.
