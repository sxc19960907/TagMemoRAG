# Design

## Boundary

This task adds eval/diagnostic coverage only. It does not alter retrieval ranking unless the diagnostic exposes a clear, localized bug that must be fixed for the suite to work.

## Data Model

The suite uses the existing eval JSONL schema:

- `kb_name`: one shared value, `mixed_knowledge`
- `relevant`: expected source/header/text/metadata matches
- `negatives`: wrong-domain source or metadata matches that must not appear in top-k
- `tags`: domain labels such as `real-manual`, `software-docs`, and `mixed-domain`

The shared `kb_name` is intentional. It verifies cross-domain behavior inside one corpus rather than relying on separate KB selection.

## Diagnostic Script

Add `scripts/diag_mixed_domain_eval.py`.

Responsibilities:

- Optionally stage source docs into a temporary directory:
  - copy selected real manual files and sidecar metadata from `product_manuals/`
  - copy public web docs and sidecar metadata from `.tmp/general-web-eval/general_web/public_web/`
- Run `tagmemorag.eval.runner.run_eval` with local hashing config by default.
- Use relaxed suite-level thresholds by default so the report is driven by per-case thresholds and negatives.
- Emit a bounded JSON report containing summary metrics, failed case ids, and actual top-k metadata already bounded by the eval reporter.

The script reuses existing eval runner, parser, metadata narrowing, and matching behavior. No duplicate retrieval logic should be introduced.

## Test Strategy

Unit tests create a tiny mixed corpus under `tmp_path` with manual-like and software-doc-like markdown files, then run the diagnostic against a temporary JSONL suite. This keeps tests offline while proving:

- one shared KB can serve both domains
- positive expectations are matched
- wrong-domain negatives are enforced

Live/manual validation is performed by running the script against `product_manuals/` plus already materialized public web docs.

