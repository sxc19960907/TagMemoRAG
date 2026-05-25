# Design

## Boundary

This task verifies the same-page ordering flag through `tagmemorag eval run`.
The feature remains default-off. The eval runner may be wired to honor the flag,
but no default-on rollout occurs in this child.

## Eval Runner Wiring

`run_eval` currently uses `execute_search` directly. To validate the runtime
flag consistently, apply `order_same_page_results` to `execution.results` after
search and before matching when:

- `cfg.search.same_page_ordering_enabled` is true
- `cfg.search.same_page_ordering_min_group_size` controls dominance threshold

When disabled, the result list remains unchanged.

## Validation Slices

Primary:

- `tests/fixtures/eval/general_web.jsonl`
- docs: `.tmp/general-web-eval/general_web`
- config: `examples/config/local-hashing-npz.yaml` plus a temporary local config
  enabling same-page ordering

Guard:

- `scripts/diag_mixed_domain_eval.py --stage-from-defaults` when local
  `product_manuals/` and `.tmp/general-web-eval/general_web` exist.

## Gate Shape

Generate:

- candidate general-web eval report
- candidate ranking-pressure report
- batch gate output comparing baseline readiness/pressure to candidate pressure

The gate must also fail when a candidate introduces new pressure case ids, even
if aggregate pressure count does not increase. This task hardens that check
because explicit eval showed a candidate can trade old pressure cases for new
ones.

Generated files stay under `.tmp/` and are not committed.

## Rollback

Rollback is disabling the flag. Code rollback removes the eval-runner wiring and
tests; runtime `/retrieve` default-off behavior remains covered by the previous
child.
