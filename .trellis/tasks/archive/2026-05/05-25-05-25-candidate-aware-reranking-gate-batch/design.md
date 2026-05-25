# Design

## Boundary

`src/tagmemorag/reranking_gate_batch.py` remains the orchestrator for offline
release-readiness plus reranking-gate checks. It should not know how to inspect
raw eval case internals beyond calling a ranking-pressure diagnostic helper.

The existing script-level diagnostic logic in
`scripts/diag_general_web_ranking_pressure.py` will move into a package module:

- `src/tagmemorag/general_web_ranking_pressure.py`

The script becomes a thin CLI wrapper around that module. This lets batch code
reuse the same bounded report contract without importing from `scripts/`.

## CLI Contract

Add:

```text
scripts/reranking_gate_batch.py \
  --candidate-eval-report <eval-output-json>
```

Behavior:

- If `--candidate-ranking-pressure` is present, use it as today.
- Else if `--candidate-eval-report` is present, derive:
  `<output-dir>/candidate-ranking-pressure.json`
  and pass that to the gate as the candidate pressure report.
- Else preserve current behavior by comparing baseline pressure to itself.

## Report Contract

The batch summary keeps the existing schema version. The `reports` map gains
`candidate_ranking_pressure` only when the batch generated or used a distinct
candidate pressure report.

The derived pressure report uses the existing
`general_web_ranking_pressure.v1` schema.

## Privacy

The ranking-pressure diagnostic already omits raw query text and snippets from
its serialized report. Tests should assert the batch summary and generated
pressure report do not contain known raw fixture strings or `actual_top_k`.

## Compatibility

No runtime retrieval behavior changes. The same-page ordering flag remains
default-off.
