# Production pilot runbook

## Goal

Provide an operator-facing production pilot runbook and a deterministic pilot command that proves the currently shipped MVP surfaces compose before a real pilot rollout.

## Requirements

- Operators can run one command against a config/profile and get a machine-readable pilot report.
- The pilot composes the existing static config validation, live-provider probe surface, deterministic readiness smoke, and retrieval eval fixture instead of duplicating their logic.
- The default pilot path is safe for local/offline use with the hashing NPZ profile and the coffee fixture.
- Remote/provider checks remain explicit and safe: unavailable optional providers may be reported as skipped, while explicitly failing configured stages fail the pilot.
- The pilot report must summarize stage status and eval metrics without emitting raw eval queries, snippets, vectors, source-file lists, API keys, or provider secrets.
- Documentation must explain when to use `config validate`, `provider probe`, `readiness smoke`, `eval run`, and the new pilot command in a production rollout.

## Acceptance Criteria

- [ ] `python -m tagmemorag pilot run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures` exits 0 in a clean local environment.
- [ ] The pilot supports JSON and Markdown report output, including status, stage summaries, sanitized eval metrics, and next-step guidance.
- [ ] Failing required stages produce a non-zero CLI exit and preserve enough sanitized detail for operators to diagnose the failing stage.
- [ ] Unit coverage exercises the pilot report contract and CLI wiring without requiring network access.
- [ ] The production deployment documentation links the pilot flow and explains how to retain the generated evidence bundle/report.

## Notes

- This task does not make the system "production-grade"; it adds a bounded pre-pilot gate for the MVP capabilities already shipped.
