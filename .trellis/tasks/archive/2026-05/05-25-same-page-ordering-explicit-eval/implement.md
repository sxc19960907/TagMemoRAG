# Implementation Plan

## Steps

- [x] Wire `run_eval` to apply `order_same_page_results` only when
      `search.same_page_ordering_enabled=true`.
- [x] Add eval-runner tests for default-off unchanged behavior and enabled
      improvement on a same-page pressure fixture.
- [x] Harden the reranking gate so candidate reports cannot introduce new
      ranking-pressure case ids.
- [x] Refine the runtime heuristic to preserve rank-1 results with sufficient
      bounded usefulness.
- [x] Run focused tests:
      `.venv/bin/pytest tests/unit/test_eval_runner.py tests/unit/test_retrieval.py tests/unit/test_config_env.py tests/unit/test_same_page_ordering_candidate.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py -q`
- [x] Create a temporary local config under `.tmp/` enabling same-page ordering.
- [x] Run explicit general-web eval with retained docs.
- [x] Generate candidate ranking-pressure report from the explicit eval.
- [x] Run reranking gate batch with candidate ranking-pressure.
- [x] Run mixed-domain guard diagnostic if local docs are available.
- [ ] Update parent program log.
- [ ] Commit and archive this child.

## Review Gates

- Default-off eval behavior must remain unchanged.
- No generated `.tmp/` files committed.
- No raw query/snippet diagnostics committed.
- Gate must pass before recommending any rollout.

## Eval Commands

General-web candidate:

```bash
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/general_web.jsonl \
  --docs .tmp/general-web-eval/general_web \
  --config .tmp/eval/same-page-enabled.yaml \
  --kb general_web \
  --top-k 5 \
  --output .tmp/eval/same-page-enabled-general-web.json
```
