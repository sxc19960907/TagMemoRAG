# Trial Report Retention CI Handoff Design

## Scope

This child task is documentation and verification only. It does not change CI behavior.

## Handoff Contract

- Local retained evidence lives under `.tmp/trial-ops-pilot/` by default.
- The retained JSON report path is `.tmp/trial-ops-pilot/report.json`.
- The browser QA stage is included by running `pilot run --include-browser-qa`.
- Broad browser changes should add `--browser-qa-full`.
- GitHub Actions remains authoritative after push and currently runs unit/e2e plus hashing eval baseline gates.

## Risk Controls

- Do not add browser QA to default CI in this pass; it can increase runtime and needs Playwright browser setup.
- Do not commit generated `.tmp/` reports.
- The handoff should point to existing runbooks instead of duplicating every pilot option.
