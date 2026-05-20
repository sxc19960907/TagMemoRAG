# Pilot eval gate diagnosis

## Goal

Extend the production pilot report so it can include the suite-level production-embedder reauthoring diagnosis, allowing a pilot reviewer to see whether eval results are strict, informational, or require follow-up before opening pilot traffic.

## Requirements

- Reuse the existing hashing-vs-production baseline diagnosis logic from code shared by scripts and pilot.
- Add optional pilot parameters for hashing baseline and production baseline paths.
- When both baselines are supplied, add an `eval_reauthoring_diagnosis` stage to the pilot report.
- The diagnosis stage must include bounded summary counts, highest severity, and top suite recommendations; it must not include raw eval queries, snippets, vectors, or full result payloads.
- Diagnosis findings should not make the local MVP pilot fail by default; they should produce `warning` when follow-up is needed and `passed` when all suites are `ok`.
- Documentation must explain that this is a pilot-review signal, not a SiliconFlow CI gate.

## Acceptance Criteria

- [ ] `run_production_pilot(..., hashing_baseline_path=..., production_baseline_path=...)` includes an `eval_reauthoring_diagnosis` stage.
- [ ] `tagmemorag pilot run` supports baseline flags and emits the diagnosis stage in JSON/Markdown.
- [ ] The existing `scripts/diagnose_eval_reauthoring.py` continues to work and uses the shared implementation.
- [ ] Unit tests cover stage warning behavior, bounded summary output, CLI wiring, and script compatibility.
- [ ] Docs show how to attach baseline diagnosis to a pilot report.

## Notes

- This task does not change fixture JSONL or baseline files.
