# Readiness smoke command — Design

## Boundary

This task adds an operator CLI smoke check. It does not add a server endpoint, a new persistent schema, or production provider validation.

The command lives under:

```text
tagmemorag readiness smoke
```

Implementation should keep orchestration in a small helper module rather than bloating `cli.py`. `cli.py` should parse arguments, call the helper, print JSON, and map pass/fail to exit code.

## Data Flow

1. Create an isolated workspace:
   - default: temporary directory removed on success
   - `--workdir`: caller-selected parent/workspace
   - `--keep-workdir`: preserve artifacts and report path
2. Write deterministic fixture docs and config into the workspace.
3. Build a tiny KB with `build_kb()` and `HashingEmbedder`.
4. Set API module globals only inside the process to reuse existing `/answer` and `/retrieve` contracts through `TestClient` or direct app call.
5. POST `/answer` with `answer.enabled=true` and provider `noop`.
6. Flush QueryPlan writer and verify the returned `plan_id` exists in `{data_dir}/{kb}/query_plans.db`.
7. Use manual-library service functions to create/export/import a bundle in the same workspace.
8. Return a JSON-safe report with per-check statuses.

## Report Contract

Suggested shape:

```json
{
  "schema_version": "readiness_smoke.v1",
  "status": "passed",
  "checks": [
    {"name": "build", "status": "passed", "detail": {"chunks": 1}},
    {"name": "retrieve_answer", "status": "passed", "detail": {"plan_id": "..."}},
    {"name": "queryplan", "status": "passed", "detail": {"rows": 1}},
    {"name": "bundle_roundtrip", "status": "passed", "detail": {"manuals": 1}}
  ],
  "workdir": null
}
```

Failure details must be bounded and low-cardinality: exception type, failed check name, and short reason. Do not include raw fixture text, local asset storage keys, vectors, checksums, API keys, or full DB rows.

## Compatibility

- The command is additive.
- It uses the existing local config model and service boundaries.
- It should not require a running server, Qdrant, S3, or network.
- Existing CLI behavior remains unchanged.

## Rollback

Reverting the helper module, CLI parser branch, tests, and docs removes the command without storage migration or data cleanup.
