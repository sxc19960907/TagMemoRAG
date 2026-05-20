# Stage 0 — Impact Audit

## Files reading `tests/fixtures/eval/*.jsonl` outside `tests/`

| File | What it reads | Impact of Phase A changes |
|------|---------------|---------------------------|
| `scripts/run_eval_ci.py` | All suite jsonls + baselines | Re-capture in Stage 6 covers it; no code change needed. |
| `scripts/diag_pyramid_dynamic_boost.py` | Only `question`/`query` field via `_load_queries` | Phase A may drop a query (D6.g) — diag total query count drops by 1 max, no schema break. |
| `scripts/diag_epa_logic_depth.py` | Same as diag_pyramid (only `query`) | Same as above. |
| `scripts/build_eval_baseline.py` | All suite jsonls + writes baselines | Stage 6 re-runs it explicitly. |
| `docs/eval-baseline-workflow.md` | Documents the baseline lifecycle | Needs update in Stage 8 to mention coffee.jsonl rewrite + Phase B follow-up. |
| `docs/system-test-plan.md:165` (SYS-K01) | Uses coffee.jsonl as smoke fixture | Test description still works; only ground truth content changes. |
| `docs/wave-phase1-architecture.md:575` | Documents baselines/ dir | Already mentions hashing vs siliconflow split; needs Phase A note in Stage 8. |

**Conclusion**: no diag-script breakage risk. Phase A changes restricted to `coffee.jsonl` ground truth + baselines do not affect any non-eval pipeline.

## Backups (Stage 0 deliverables)

- `research/hashing-pre-rewrite-snapshot.json` — pre-rewrite hashing baseline (used by Stage 6 `--compare-with` to enforce D6 sanity check).
- `research/siliconflow-pre-rewrite-snapshot.json` — pre-rewrite siliconflow baseline (used by Stage 6 to compute post-rewrite delta for commit message).

These files live in the task directory (not under `tests/`) so they're not picked up by future eval runs.
