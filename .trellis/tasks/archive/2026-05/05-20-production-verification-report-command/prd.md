# Production verification report command

## Goal

Add a local reporting command that turns the production environment verification checklist into a repeatable retained JSON/Markdown artifact, while keeping live provider calls opt-in and safe.

## Requirements

- Provide a script or CLI entry point that runs deterministic verification steps:
  - static config validation
  - local readiness smoke
  - pilot report
- Include optional live provider probes only when the operator explicitly requests them.
- Write a sanitized aggregate verification report to JSON or Markdown.
- Record command outcomes and artifact paths, not raw secrets, raw provider responses, raw document text, vectors, or bearer tokens.
- Use the existing config validation, provider probe, readiness, and pilot modules rather than shelling out where practical.

## Acceptance Criteria

- [ ] A command can produce a JSON report for `examples/config/local-hashing-npz.yaml` without live provider calls.
- [ ] A command can produce a Markdown report for the same local profile.
- [ ] Optional provider probes are represented as skipped/omitted unless explicitly requested.
- [ ] Unit tests cover success and optional probe selection behavior.
- [ ] Docs mention the command as the executable companion to the checklist.

## Out of Scope

- Automatically running live provider probes by default.
- Adding new provider implementations.
- Storing secrets or reading `.env` values into reports.
- Opening/pushing a PR unless explicitly requested after implementation.
