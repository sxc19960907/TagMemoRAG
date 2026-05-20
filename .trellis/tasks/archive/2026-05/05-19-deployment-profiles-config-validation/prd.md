# Deployment profiles and config validation

## Goal

Make common deployment modes easier to copy, inspect, and validate before an operator starts the service or runs a rebuild.

This task adds example config profiles and a static/local config validation command. It complements `tagmemorag readiness smoke`: profile validation answers "is this config coherent and locally satisfiable?", while readiness smoke answers "do core MVP paths compose in this checkout?".

## Confirmed Facts

- `Settings` already models local/hash/http embedding, NPZ/Qdrant vector storage, file/SQLite manual registry, local/S3 blob store, reranker, answer, OCR, visual retrieval, connectors, metrics, and tracing.
- `load_config()` already applies `environment > .env > YAML > defaults`.
- README and `docs/production-deployment-operations.md` document Qdrant, S3, registry/blob, readiness smoke, and provider key env names.
- Existing config tests cover env overrides but there is no operator command that summarizes config readiness or validates common profile pitfalls.
- Network/live provider checks should stay opt-in future work.

## Requirements

- Add example config profiles for the most common local and deployment shapes:
  - local hashing + NPZ
  - SQLite registry + local blobs
  - Qdrant
  - S3-compatible blobs
  - OpenAI-compatible answer provider
- Add `tagmemorag config validate --config <path>` that:
  - loads the config using existing precedence
  - returns JSON by default
  - reports `status: passed|warning|failed`
  - reports bounded per-check results without secrets, raw documents, vectors, or absolute source inventories
  - checks local path writability for local storage/blob/registry modes
  - checks required env var presence for configured remote providers without printing values
  - warns when optional extras are likely required (`qdrant-client`, `boto3`) but not importable
  - warns when `/metrics` is missing from auth public paths while auth and metrics are enabled
  - fails when static requirements are incoherent, such as S3 blob mode without `s3_bucket`
- Document how profile validation differs from readiness smoke and `/ready`.
- Keep validation static/local: do not call Qdrant, S3, embedding, reranker, answer, OCR, or visual providers.

## Acceptance Criteria

- [ ] Example profile files exist and load with `load_config()`.
- [ ] `tagmemorag config validate --config <profile>` exits `0` for healthy local profiles.
- [ ] Validation emits JSON with stable schema version, aggregate status, and per-check entries.
- [ ] Missing required env vars for configured remote providers are reported by env var name only, never by value.
- [ ] S3 profile without bucket fails; Qdrant/S3 missing optional Python extras warn rather than connecting to services.
- [ ] CLI/unit tests cover pass, warning, and failure cases.
- [ ] README and production operations docs explain profiles, `config validate`, readiness smoke, and `/ready`.
- [ ] Final validation includes config/CLI focused tests and `git diff --check`.

## Out Of Scope

- Live network health checks.
- Remote provider smoke calls.
- Secret managers or secret value validation.
- Auto-mutating config files.
- Replacing `config.yaml` as the default developer config.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
