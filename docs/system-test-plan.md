# TagMemoRAG System Test Plan

## 1. Test Objective

Verify TagMemoRAG as a complete product, not only as isolated modules. The test suite should prove that users can build and operate knowledge bases, search product manuals, manage manual content, govern tags, collect retrieval feedback, observe service health, and recover from failures without data loss.

## 2. Scope

In scope:

- CLI workflows: build, search, eval, auth key generation, manual bulk import, manual library rebuild/dirty export, tag governance, feedback, Qdrant inspection.
- FastAPI workflows: search, rebuild, anchors, graph info, manual library, bulk import, tag governance, feedback, KB listing, cache clearing, health, readiness, metrics.
- Admin Web UI: manual library and retrieval quality pages.
- Storage backends: local NPZ and optional Qdrant vector store.
- Cross-cutting behavior: auth, KB isolation, rate limiting, cache invalidation, structured errors, logging, metrics, tracing configuration, shutdown/rebuild concurrency.
- Data formats: Markdown, text, text-based PDF, metadata sidecars, JSON/JSONL/CSV bulk metadata.

Out of scope:

- OCR for scanned PDFs.
- Quality of third-party embedding models beyond integration contract.
- Browser compatibility beyond current evergreen Chromium/Safari/Firefox unless a product requirement is added.

## 3. Test Environment

Recommended baseline:

- Python 3.11 or newer.
- `uv sync --extra dev`.
- Default local vector backend `npz`.
- Test config uses `model.name=hashing` or the in-process fake/hash embedder for deterministic runs.
- Fixtures from `tests/fixtures/`, plus a larger synthetic manual corpus for performance and stress cases.

Optional environment:

- Qdrant running at `http://localhost:6333`.
- `uv sync --extra qdrant`.
- Auth-enabled config with at least three API keys: search-only, rebuild-scope, admin-scope.

## 4. Acceptance Gates

- P0 and P1 test cases pass before release.
- No P0 data loss, cross-KB leakage, stale-search, auth bypass, or rebuild-swap regression remains open.
- API error responses keep the documented `{code, message, detail}` shape.
- Health, readiness, and metrics behavior is stable under normal startup, rebuild, failure, and shutdown paths.
- Performance budgets are met for the agreed corpus size and hardware profile.

## 5. System Test Cases

### A. Installation, Configuration, and Startup

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-A01 | P0 | Fresh install and CLI discovery | Clean checkout | Run `uv sync --extra dev`; run `python -m tagmemorag --help` and `tagmemorag --help`. | Install succeeds; both entrypoints show available commands without importing/downloading a model unexpectedly. |
| SYS-A02 | P0 | Default config loads | `config.yaml` present | Start API with `python -m tagmemorag serve --host 127.0.0.1 --port 8000 --config config.yaml`. | Server starts, structured startup logs are emitted, `/health` returns 200. |
| SYS-A03 | P1 | Environment variables override YAML | Set `TAGMEMORAG__SERVER__PORT`, `TAGMEMORAG__STORAGE__DATA_DIR`, and `TAGMEMORAG__MODEL__NAME=hashing`. | Start server and inspect effective behavior. | Server binds overridden port, writes data under overridden path, uses overridden model config. |
| SYS-A04 | P1 | Invalid config fails clearly | Config contains invalid vector provider or malformed numeric settings. | Start CLI/API. | Process fails before serving; error message identifies invalid field; no partial KB artifacts are written. |
| SYS-A05 | P2 | Startup warmup failure | Configure missing HTTP embedding API key or unreachable embedding URL. | Start API. | Startup exits or readiness stays unavailable according to contract; logs include safe error type without leaking secrets. |

### B. Document Parsing and KB Build

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-B01 | P0 | Build KB from Markdown manuals | Fixture directory with Markdown and sidecar metadata. | Run `python -m tagmemorag build --docs tests/fixtures/product_manuals --kb product-a --config test.yaml`. | Command exits 0; output includes `kb_name`, `build_id`, and positive chunk count; graph/vector/metadata files exist under `data/product-a`. |
| SYS-B02 | P0 | Build KB from mixed `.md`, `.txt`, text PDF | Corpus contains all supported suffixes. | Build KB and inspect graph info. | Supported files are indexed; PDF pages with embedded text become searchable chunks; unsupported files are ignored or reported without failing the build. |
| SYS-B03 | P1 | Fallback metadata when sidecar is missing | Manual without `.metadata.json`. | Build KB and query `/manuals`. | Manual appears with fallback `manual_id`, title/source path/category/language as documented. |
| SYS-B04 | P0 | Invalid sidecar blocks unsafe build | Sidecar has duplicate manual ID, invalid tags, empty required fields, or unsafe source path. | Run build. | Build fails with clear validation error; no corrupt saved KB replaces a previously valid KB. |
| SYS-B05 | P1 | Parser respects heading hierarchy and chunk limits | Manual with nested headings, long paragraphs, and short sections. | Build and inspect search result headers/text snippets. | Chunks preserve useful headers, split long text, and do not merge unrelated headings. |
| SYS-B06 | P1 | Repeat build is deterministic enough for operations | Same corpus and config. | Build same KB twice. | Build succeeds both times; node counts and manual facets remain stable; old artifacts are safely overwritten only after successful save. |

### C. CLI Search and Retrieval Quality

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-C01 | P0 | Search built KB from CLI | KB built from coffee fixture. | Run `python -m tagmemorag search "蒸汽很小" --kb default --top-k 5 --config test.yaml`. | JSON response contains `build_id` and ranked results with score, text, path, header, anchor key, and manual metadata. |
| SYS-C02 | P0 | Metadata filters narrow results | Multi-category/product corpus built. | Search with `--category`, `--model`, `--language`, and repeated `--tag`. | All returned results belong to the requested metadata scope; zero-match filter returns empty results, not unrelated chunks. |
| SYS-C03 | P1 | Search parameter overrides | Built KB. | Run searches with different `--top-k`; API variant with `steps`, `decay`, `aggregate`. | Result count and ranking behavior reflect request parameters; invalid aggregate is rejected. |
| SYS-C04 | P1 | Debug search metadata is safe | Built KB. | Run CLI with `--debug-search` and API request with `debug=true`. | Debug payload includes strategy/candidate/parameter diagnostics; raw query text, vectors, trace IDs, and candidate ID dumps are absent. |
| SYS-C05 | P1 | Query variants and multilingual terms | Product manual corpus with Chinese and English terms. | Search using exact product symptom, synonym-ish wording, and mixed Chinese/English model names. | Relevant manual sections appear in top K according to accepted threshold; metadata remains intact. |

### D. API Search, Cache, Anchors, and Graph Info

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-D01 | P0 | API search happy path | Server has loaded KB. | `POST /search` with `question`, `kb_name`, and `top_k`. | 200 response includes `trace_id`, `search_id`, `build_id`, `search_time_ms`, `cache`, and results. |
| SYS-D02 | P0 | KB not loaded error shape | Server started without requested KB. | `POST /search` with unknown `kb_name`. | Non-2xx response uses `{code, message, detail}` and a stable code such as `KB_NOT_LOADED`. |
| SYS-D03 | P0 | Cache hit/miss lifecycle | Cache enabled. | Send identical search twice; edit anchor or rebuild; send search again. | First request is miss, second hit, anchor/rebuild changes cause miss and fresh results. |
| SYS-D04 | P0 | Anchor boosts and survives rebuild by stable key | Built KB with known node. | `POST /anchor`; search; rebuild same docs; `GET /anchor`; search again. | Anchor changes ranking; anchor remains resolved after rebuild via `anchor_key`; unresolved anchors are reported if source text disappears. |
| SYS-D05 | P1 | Invalid anchor node is rejected | Built KB. | `POST /anchor` with nonexistent `node_id`. | 400-style service error; no anchor file mutation. |
| SYS-D06 | P1 | Graph info contract | Built KB with anchors. | `GET /graph_info`. | Response includes node/edge counts, `build_id`, metadata, and unresolved anchor list without dumping raw vectors. |
| SYS-D07 | P1 | Cache clear by admin | Auth enabled, admin key available. | Search twice; `POST /admin/cache/clear`; search again. | Clear endpoint returns cleared count/scope; next search is a miss. |

### E. Rebuild, Concurrency, and Shutdown

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-E01 | P0 | Async rebuild happy path | Server serving old KB. | `POST /rebuild`; poll `GET /rebuild/{task_id}`. | Initial response is 202; polling reaches completed; `build_id` changes; new graph is searchable. |
| SYS-E02 | P0 | Failed rebuild keeps old graph | Server serving valid KB; rebuild docs contain invalid metadata or simulated embed failure. | Trigger rebuild and poll. | Task fails with error detail; old search results and old `build_id` remain active. |
| SYS-E03 | P0 | Concurrent rebuild on same KB rejected | One rebuild in progress. | Submit second rebuild for same KB. | Second request is rejected with clear conflict; first rebuild continues. |
| SYS-E04 | P1 | Rebuilds for different KBs can run independently | Two KBs configured. | Trigger rebuild for both KBs. | Tasks execute without cross-KB state collision; each KB serves its own graph. |
| SYS-E05 | P1 | Shutdown drains rebuild safely | Rebuild in progress. | Send shutdown/stop server. | Server begins shutdown, waits for rebuild lock/drain up to timeout, logs safe completion; no partial artifacts replace active KB. |

### F. Managed Manual Library

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-F01 | P0 | Validate metadata without writing | Auth key has rebuild scope. | `POST /manuals/validate` with valid metadata. | 200 response includes normalized metadata and warnings/errors arrays; no source or sidecar files created. |
| SYS-F02 | P0 | Upload new manual | Valid Markdown file and metadata. | `POST /manuals` multipart with `overwrite=false`; `GET /manual-library`. | Source and sidecar are created under safe library path; manifest marks rebuild required; manual is visible before rebuild but not necessarily searchable. |
| SYS-F03 | P0 | Rebuild managed library full mode | Dirty library after upload. | `POST /manual-library/rebuild` with `mode=full`; poll task. | Task completes; dirty state clears; uploaded manual becomes searchable; impact summary is written. |
| SYS-F04 | P0 | Incremental rebuild reuses unchanged chunks | Existing built library; edit one manual. | Replace or patch manual; rebuild `mode=incremental`; inspect task metadata and search. | Dirty manual is rebuilt; unchanged chunks are reused; changed content is searchable; removed content no longer appears. |
| SYS-F05 | P1 | Auto rebuild mode threshold behavior | Configure low auto thresholds. | Mark many manuals dirty; rebuild `mode=auto`. | Effective mode chooses full when thresholds are exceeded and reports `auto_decision_reason`. |
| SYS-F06 | P0 | Incremental strict mode without fallback | Remove old graph or chunk identity; request `mode=incremental`, `allow_fallback=false`. | Trigger rebuild. | Task fails clearly instead of silently full rebuilding; dirty state remains pending. |
| SYS-F07 | P0 | Update metadata and replace file | Manual exists. | `PATCH /manuals/{manual_id}/metadata`; `PUT /manuals/{manual_id}/file`; rebuild. | Sidecar/source update succeeds; manifest pending state is correct; search returns updated metadata/content after rebuild. |
| SYS-F08 | P0 | Disable, hard delete, and rebuild | Manual exists; admin key for hard delete. | `DELETE /manuals/{id}` soft; rebuild; then hard delete with `hard=true`. | Disabled manual remains listed but not searchable after rebuild; hard delete removes source/sidecar and requires admin scope. |
| SYS-F09 | P0 | Unsafe path and unsupported suffix rejected | Upload metadata with traversal path or `.exe` file. | Validate/upload/import. | Request is rejected; no files are written outside library root. |
| SYS-F10 | P1 | Dirty export JSON and CSV | Dirty library exists. | `GET /manual-library/dirty?format=json`; `format=csv`; CLI `manual-library dirty`. | JSON includes pending changes, searchable/exists flags, build IDs, recovery actions, summaries; CSV contains stable compact columns. |

### G. Bulk Import

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-G01 | P0 | Bulk preview CSV happy path | CSV metadata and matching files. | `POST /manual-library/bulk/preview` with `metadata_format=csv`. | Preview returns row table with create/update/skip actions and no writes. |
| SYS-G02 | P0 | Bulk import selected valid rows | Preview has multiple valid rows. | `POST /manual-library/bulk/import` with `selected_rows`. | Only selected valid rows are imported; manifest marks rebuild required; result references row numbers. |
| SYS-G03 | P0 | Bulk import rejects invalid selected row | Metadata includes duplicate ID, missing file, unsafe path, unsupported suffix. | Preview, then import invalid selected row. | Import fails with row-level errors; no partial selected invalid row is written. |
| SYS-G04 | P1 | JSON, JSONL, and CSV parity | Equivalent metadata in each format. | Preview/import each format. | Same validation semantics and normalized records across formats. |
| SYS-G05 | P1 | Conflict modes | Existing manual present. | Import with `create_only`, `upsert`, and `dry_run`. | `create_only` rejects conflict; `upsert` updates only with explicit overwrite; `dry_run` writes nothing. |

### H. Tag Governance and Suggestions

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-H01 | P0 | Save advisory tag policy | Rebuild-scope key. | `PUT /manual-library/tags/policy`; then `GET /manual-library/tags`. | Policy persists; stats show canonical tags, usage counts, synonyms, deprecated tags, and drift issues. |
| SYS-H02 | P0 | Strict policy blocks invalid tags | Strict policy configured. | Validate/upload manual with unknown or deprecated tags. | Validation returns errors and upload/import is blocked. |
| SYS-H03 | P1 | Advisory policy warns but allows | Advisory policy configured. | Validate/upload manual with synonym/deprecated/unknown tag. | Warnings are returned; writes may proceed when no hard errors exist. |
| SYS-H04 | P0 | Search resolves tag synonyms | Policy maps synonym to canonical tag. | Search/filter with synonym tag. | Results match canonical tag content without rewriting sidecars. |
| SYS-H05 | P0 | Rewrite preview and commit | Manuals use old tag. | `POST /manual-library/tags/rewrite/preview`; then `/rewrite`. | Preview writes nothing; commit updates sidecars, optionally updates policy, marks rebuild pending, and reports changed manuals. |
| SYS-H06 | P1 | Tag suggestions are deterministic and bounded | Draft metadata/text sample. | `POST /manuals/tags/suggest` repeatedly with same payload and different limits. | Suggestions are normalized, scored, capped by limit, exclude existing draft tags, prefer policy canonical tags, and hide deprecated tags. |

### I. Authentication, Authorization, and Rate Limiting

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-I01 | P0 | Public endpoints stay public | Auth enabled. | Call `/health`, `/ready`, `/metrics`, `/docs`, `/openapi.json` without token. | Public endpoints respond according to service state; no auth challenge unless config intentionally removes public path. |
| SYS-I02 | P0 | Missing/invalid token rejected | Auth enabled. | Call protected search/manual endpoints without token and with bad token. | 401 `UNAUTHORIZED`; no operation side effects. |
| SYS-I03 | P0 | Scope enforcement | Keys for `search`, `rebuild`, and `admin`. | Attempt search, upload, rebuild, feedback review, hard delete, cache clear with each key. | Each operation requires documented scope; insufficient scope returns 403. |
| SYS-I04 | P0 | KB allowlist enforcement | Key limited to `product-a`. | Search/list/rebuild `product-b`. | 403 and no leakage of product-b data or metadata. |
| SYS-I05 | P0 | Rate limit exceeded | Key has tiny rate limit. | Send requests until over limit. | 429 `RATE_LIMITED`; `Retry-After` and `X-RateLimit-*` headers are present; other keys are unaffected. |
| SYS-I06 | P1 | Generated API key works | CLI available. | Run `tagmemorag auth generate-key`; add hash to config; call API with plaintext key. | Generated hash verifies; plaintext is only shown at generation time; revoked or changed keys fail. |

### J. Feedback and Evaluation Promotion

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-J01 | P0 | Submit feedback from search result | Search response has `trace_id` and `search_id`. | `POST /search/feedback` with bounded selected/expected results. | Feedback JSONL row is appended with generated ID and status `new`; payload is bounded and safe. |
| SYS-J02 | P0 | List and review feedback | Admin key. | `GET /search/feedback`; `PATCH /search/feedback/{id}`. | Filters by status/outcome/query work; review status and operator note persist. |
| SYS-J03 | P1 | Invalid feedback rejected | Oversized payload, unsafe fields, missing required query/outcome. | Submit feedback. | Request fails with validation error; no JSONL corruption. |
| SYS-J04 | P0 | Promotion preview writes nothing | Reviewed feedback exists. | `POST /search/feedback/promote/preview`. | Eval case preview follows eval schema; unusable feedback is skipped with reasons; output file unchanged. |
| SYS-J05 | P0 | Promotion append/overwrite semantics | Existing eval draft file. | Promote with neither flag, with `append`, and with `overwrite`. | Existing file is protected unless explicit; promoted feedback is marked; JSONL remains valid. |
| SYS-J06 | P1 | CLI feedback parity | Feedback JSON file exists. | Use `feedback submit/list/review/promote-preview/promote`. | CLI outputs JSON and matches API behavior. |

### K. Evaluation CLI and Quality Thresholds

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-K01 | P0 | Eval suite passes known fixture | Coffee/product manual fixture. | `python -m tagmemorag eval run --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --config test.yaml`. | Report exits 0 and includes precision/recall/MRR/hit@K plus search parameters. |
| SYS-K02 | P0 | Eval threshold failure exits nonzero | Set unrealistically high threshold. | Run eval. | Command exits nonzero; report identifies failed thresholds. |
| SYS-K03 | P1 | Eval can reuse built KB | KB already built. | Run eval with `--reuse-built-kb`. | Eval uses existing artifacts and reports KB/build metadata. |
| SYS-K04 | P1 | Eval dataset validation | JSONL has bad JSON, duplicate ID, invalid matcher, empty relevant set. | Run eval. | Each invalid suite fails with line-aware error. |

### L. Admin Web UI

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-L01 | P1 | Manual library page loads | Server running. | Open `/admin/manual-library`. | HTML shell loads; static JS/CSS return 200; no console errors on first load. |
| SYS-L02 | P1 | Manual library UI core workflow | Auth token available if enabled. | In browser: set token, select KB, upload manual, validate metadata, filter table, edit metadata, trigger rebuild. | UI calls correct APIs, shows success/error states, refreshes dirty/searchable state, and does not expose token outside session storage. |
| SYS-L03 | P1 | Bulk import UI workflow | CSV and files prepared. | Use preview/import controls. | Preview table shows row actions/errors; import selected rows works; invalid rows are visibly blocked. |
| SYS-L04 | P1 | Tag governance UI workflow | Policy and drift available. | Open policy/stats/rewrite controls. | Drift and counts render; preview is distinct from commit; commit marks rebuild pending. |
| SYS-L05 | P1 | Retrieval quality page loads and works | Feedback rows exist. | Open `/admin/retrieval-quality`; filter/review/promote preview. | Static assets load; feedback list, filters, review, and preview actions work with visible errors for auth/scope failures. |
| SYS-L06 | P2 | Responsive layout smoke test | Browser automation available. | Check desktop and mobile widths for both admin pages. | Controls remain usable; text does not overlap; no horizontal overflow for primary workflows. |

### M. Multi-KB Isolation

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-M01 | P0 | Build and serve two KBs | Product A and B corpora. | Build both; start server; call `/kb`; search both. | `/kb` lists both with separate build IDs/node counts; each search returns only its KB data. |
| SYS-M02 | P0 | Anchors, cache, feedback, dirty state are KB-scoped | Two KBs loaded. | Add anchor/cache/feedback/dirty manual in product-a; inspect product-b. | No product-a state appears in product-b. |
| SYS-M03 | P0 | Auth KB allowlist filters `/kb` | Auth enabled. | Call `/kb` with wildcard, product-a-only, and product-b-only keys. | Response lists only allowed KBs. |

### N. Observability and Error Handling

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-N01 | P0 | Health and readiness states | Server startup, no KB, loaded KB, shutdown. | Call `/health` and `/ready` at each state. | `/health` stays process-liveness 200; `/ready` is 503 until embedder ready and KB loaded, then 200, then 503 during shutdown. |
| SYS-N02 | P0 | Metrics endpoint exposes bounded labels | Metrics enabled. | Perform searches, cache hits, rate limit, rebuild, feedback; call `/metrics`. | Metrics include expected counters/gauges/histograms; labels are low-cardinality and contain no query text, raw paths, API keys, or vectors. |
| SYS-N03 | P1 | Metrics disabled | Config disables metrics. | Call metrics path. | Endpoint returns disabled/not found behavior per config; no crash. |
| SYS-N04 | P1 | Trace IDs | Send search with and without `X-Request-ID`. | Inspect response/logs. | Server generates trace ID when absent and respects safe client trace ID when present. |
| SYS-N05 | P0 | Unexpected exception wrapping | Simulate service exception. | Call affected endpoint. | Response is structured internal error; logs contain stack context; client does not see secrets or raw traceback. |
| SYS-N06 | P1 | Logging format | JSON and console modes. | Run CLI/API operations. | Logs are parseable in JSON mode and human-readable in console mode; context vars do not bleed across requests. |

### O. Qdrant Vector Backend

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-O01 | P1 | Build and search with Qdrant | Qdrant running; provider=qdrant. | Build KB; search CLI/API. | Qdrant collection is created; graph loads vectors by node ID; search works. |
| SYS-O02 | P1 | ANN preselection path | Qdrant KB and `ann_preselect_enabled=true`. | Search with and without filters. | Debug metadata reports ANN strategy; filtered results stay inside metadata scope. |
| SYS-O03 | P0 | ANN fallback on Qdrant failure | Qdrant temporarily unavailable after KB load. | Search. | Search falls back to exact/local graph behavior when supported and reports fallback safely; no 500 for recoverable ANN failure. |
| SYS-O04 | P1 | Qdrant inspect is safe and useful | Qdrant collection exists. | Run `tagmemorag qdrant inspect --kb default`. | JSON report includes collection/counts/missing graph vectors/payload key coverage/recommendations; no raw vectors/text/secrets. |
| SYS-O05 | P0 | Qdrant sync failure preserves old graph | Managed library rebuild with Qdrant; simulate sync failure. | Trigger rebuild. | Task fails; old loaded graph remains active; dirty state remains pending; stale deletes are not attempted before required upserts. |
| SYS-O06 | P1 | Incremental Qdrant sync reuses payloads | Existing compatible `chunk_identity.json`. | Edit one manual; rebuild incremental. | New/changed points upsert; reused payloads refresh; stale points delete after successful upserts; sync summary counts are correct. |

### P. Security, Data Safety, and Robustness

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-P01 | P0 | Path traversal defense | Manual upload/import/delete payloads use `../`, absolute paths, or encoded traversal. | Try all write endpoints and CLI bulk import. | All are rejected; no file outside configured roots is touched. |
| SYS-P02 | P0 | Secret redaction | Config has API keys/env vars. | Trigger validation, HTTP embed error, auth failure, and logs/metrics. | Responses/logs/metrics never expose bearer tokens, API keys, or hash internals beyond safe IDs. |
| SYS-P03 | P1 | Large payload bounds | Oversized text sample, feedback arrays, metadata, or upload. | Submit to API. | Request is rejected or bounded gracefully; server remains responsive. |
| SYS-P04 | P1 | Atomic writes under failure | Simulate write failure during graph, manifest, sidecar, feedback, and policy updates. | Perform operation. | Existing files remain valid; partial temp files do not become active state. |
| SYS-P05 | P1 | Restart recovery | Stop server after builds/imports/rebuilds/feedback; start again. | Inspect `/ready`, `/kb`, search, dirty state, feedback. | Persisted state reloads correctly; pending dirty state and recovery hints survive restart. |

### Q. Performance and Stress

| ID | Priority | Scenario | Preconditions | Steps | Expected Results |
| --- | --- | --- | --- | --- | --- |
| SYS-Q01 | P1 | 1,000-node build/search budget | Synthetic 1,000-node corpus. | Build and run representative searches. | Build/search complete within agreed budget; memory growth is acceptable. |
| SYS-Q02 | P1 | Repeated cached search throughput | Cache enabled, built KB. | Send repeated identical and varied searches. | Cache hit latency improves; cache size respects max entries and TTL. |
| SYS-Q03 | P1 | Concurrent search during rebuild | Server serving old KB. | Run steady search traffic while rebuild runs. | Searches continue to return old or new consistent build IDs, never partial mixed state. |
| SYS-Q04 | P2 | Bulk import scale | Large CSV/JSONL batch. | Preview and import hundreds/thousands of rows. | Validation remains bounded; row-level errors are returned without unbounded memory/output. |

## 6. Regression Suite Mapping

Recommended automated release command set:

For the current tiered local quality gates, including browser-first QA readiness and live-provider boundaries, see [RAG Quality Gates](rag-quality-gates.md). The commands below remain the lower-level system-test examples behind that gate matrix.

```bash
uv run pytest tests/unit tests/e2e
```

Recommended system smoke sequence:

```bash
python -m tagmemorag build --docs tests/fixtures/product_manuals --kb product-a --config test.yaml
python -m tagmemorag search "冰箱温度怎么调" --kb product-a --top-k 5 --config test.yaml
python -m tagmemorag eval run --suite tests/fixtures/eval/product_manuals.jsonl --docs tests/fixtures/product_manuals --config test.yaml
python -m tagmemorag manual-library dirty --kb product-a --config test.yaml --format json
```

For Qdrant-enabled release checks, add:

```bash
python -m tagmemorag qdrant inspect --kb product-a --config qdrant-test.yaml
```

## 7. Test Data Matrix

Minimum data set:

- Coffee machine troubleshooting manual with Chinese symptoms.
- Product manuals for refrigerator, air conditioner, dishwasher, and washer.
- One manual per supported file type: `.md`, `.txt`, text-based `.pdf`.
- Manuals with complete metadata, missing metadata, duplicate IDs, invalid tags, disabled/archived status, and unsafe paths.
- Bulk metadata in CSV, JSON, and JSONL.
- Tag policy with canonical tags, synonyms, deprecated tags, strict and advisory modes.
- Feedback examples for useful, missing result, bad ranking, and unusable promotion cases.

## 8. Exit Report Template

Use this short format after a full system test run:

```text
Build:
Environment:
Config:
Vector backend:
Test data:

Summary:
- Passed:
- Failed:
- Blocked:
- Not run:

P0 issues:
- ID / title / owner / status

P1 issues:
- ID / title / owner / status

Notes:
- Performance observations
- Recovery observations
- Data cleanup performed
```
