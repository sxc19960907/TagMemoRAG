# MVP Integration Acceptance And Hardening — Design

## Scope

This task adds verification, not new product surfaces. It should prove the shipped foundations compose under deterministic providers and conservative defaults.

## Acceptance Matrix

| Slice | Acceptance target | Deferred |
| --- | --- | --- |
| T1/T1.5 IndexGeneration | Existing generation/path tests plus focused regression suite in this task run | traffic split, multi-replica coordination |
| T2 QueryPlan | `/retrieve` and `/answer` produce plan ids and persist non-private plans | advanced analytics, full PII masking |
| T3 Reranker | Default disabled behavior remains unchanged; existing fallback tests run | production tuning/default-on rollout |
| T5 Replay | Existing replay unit tests run in focused suite | broad rolling production window |
| T6 Answer | `/answer` reuses `/retrieve`, noop provider works, disabled provider degrades in payload | streaming, multi-turn, real judge |
| T7 OCR | Deterministic OCR fixture can produce searchable normal chunks when enabled | production OCR, layout reconstruction |
| T8 Visual | Visual manifest attaches/appends safe evidence only when enabled and intent matches | real visual encoder/reranker |
| T9 Connectors | Fixture connector materialization builds into searchable KB | real SaaS connectors/auth/webhooks |
| Ops recovery | Bundle export/import round-trips deterministic materialized sources | encrypted/signed/streaming bundles |

## Test Shape

- Add `tests/unit/test_mvp_integration_acceptance.py`.
- Use `HashingEmbedder`, local temp dirs, FastAPI `TestClient`, and deterministic providers only.
- Prefer two or three scenario tests over a huge fragile mega-test:
  1. default-off config matrix
  2. connector -> build -> retrieve -> answer -> QueryPlan
  3. OCR/visual/bundle deterministic integration
- Use existing service functions directly where API coverage already exists and direct use is more stable.

## Safety

- No network.
- No real provider dependencies.
- No raw secrets or absolute paths in asserted public payloads.
- Any discovered large gap becomes a follow-up note in this task, not a broad implementation.

## Outcome

- Acceptance tests landed as five focused scenarios rather than one brittle mega-test.
- T2/T6 composition is covered through `/answer` reusing `/retrieve` and sharing the same `plan_id`.
- T8 public payload safety is asserted by checking visual responses omit local `storage_key` and checksum internals.
- T7 is validated at parser/graph/search level because product OCR remains an explicit opt-in ingestion path.
- Ops recovery is validated by exporting/importing deterministic connector materialization output.
