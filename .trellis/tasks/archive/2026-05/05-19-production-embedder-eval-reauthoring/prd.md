# Production embedder eval reauthoring

## Goal

Make the production-embedder eval gap explicit and actionable by adding an offline diagnostic report that compares the deterministic hashing CI baseline with the SiliconFlow/production-embedder baseline and recommends which suites need fixture reauthoring first.

## Requirements

- Provide a local, network-free command/script that reads existing baseline JSON files and produces a JSON or Markdown reauthoring diagnosis.
- Compare suite metrics across hashing and production embedder baselines, including per-metric deltas and threshold readiness.
- Rank suites by severity so the next fixture work is not chosen by intuition alone.
- Emit clear recommendations: keep as-is, monitor, reauthor fixture expectations, or investigate retrieval/model mismatch.
- Do not change fixture JSONL ground truth in this task; changing expected cases requires human review after the diagnostic report exists.
- Document how this diagnostic fits with `build_eval_baseline.py`, `run_eval_ci.py`, `pilot run`, and the existing SiliconFlow informational baseline.

## Acceptance Criteria

- [ ] A command or script can run offline against `tests/fixtures/eval/baselines/hashing.json` and `tests/fixtures/eval/baselines/siliconflow.json`.
- [ ] JSON output includes schema version, input baseline paths, summary counts, per-suite metrics, deltas, severity, and recommendation text.
- [ ] Markdown output provides a reviewer-friendly table sorted by severity.
- [ ] Unit tests cover severity classification, missing-suite handling, JSON/Markdown output, and CLI/script behavior.
- [ ] Documentation explains that the diagnostic does not make SiliconFlow a CI gate and does not automatically rewrite fixtures.

## Notes

- This is a reauthoring readiness task, not the reauthoring itself.
