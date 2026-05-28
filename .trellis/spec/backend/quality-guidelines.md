# Quality Guidelines

> Code quality standards for TagMemoRAG backend development.

---

## Overview

TagMemoRAG should be implemented as a small, testable Python package. Prefer explicit dataclasses, typed function signatures, deterministic tests, and narrow module boundaries.

M0 quality is defined by the acceptance criteria in `.trellis/tasks/05-10-wave-rag-implementation/prd.md` and the phase checklist in `implement.md`.

---

## Required Patterns

- Keep pure algorithm modules side-effect-free where practical.
- Use dataclasses for core contracts: `Chunk`, `Anchor`, `Result`, and `GraphState`.
- Normalize embeddings once and treat dot product as cosine similarity.
- Keep graph node ids as integers and store stable identity separately as `anchor_key`.
- Store vectors outside the NetworkX graph.
- Use atomic file replacement for persistent files.
- Keep rebuild double-buffer behavior: build new state off to the side, then swap only after success.
- Include `build_id` in search results and relevant logs.
- Use explicit config objects instead of scattering constants across modules.
- Keep hybrid lexical retrieval local and bounded: scan loaded graph node fields only, respect filters and KB boundaries, and keep final ranking deterministic over the loaded graph and vectors.
- Match normalized English metadata aliases on token boundaries, not substrings, so `washer` never narrows a `dishwasher` query.
- For `BaseSettings` configs that merge YAML with env vars, explicitly test precedence. The M1 contract is `env > .env > YAML init data > defaults`; pydantic-settings does not preserve that order unless `settings_customise_sources` is configured.

---

## Forbidden Patterns

- Do not use pickle for persisted graph state.
- Do not let `/search` mutate graph, anchors, config, or storage.
- Do not make algorithm modules import FastAPI, CLI, or global app state.
- Do not make rebuild failures replace or clear the currently served graph.
- Do not silently drop unresolved anchors after rebuild.
- Do not introduce new production dependencies without updating `pyproject.toml`, tests, and this spec if behavior changes.
- Do not emit raw lexical query tokens, matched document snippets, full candidate ids, vectors, or source-file lists in debug metadata, logs, metrics, traces, or cache suffixes.
- Do not hand-roll string parsing for JSON/YAML/NPZ files when standard libraries or project storage helpers are available.

---

## Testing Requirements

M0 requires focused tests for:

- Parser edge cases: empty file, no headings, nested headings, long-block split, short-block merge.
- Embedder shape and normalization. Use a fake embedder in unit tests when model download would be too expensive.
- Graph builder semantic, parent-child, sibling, and consecutive edges.
- Wave search max vs sum aggregation, anchor boost, propagation boost, and deterministic ranking.
- Storage round-trips for graph, vectors, anchors, and meta.
- AppState rebuild concurrency: searches keep using old graph while rebuild runs.
- API error format and anchor/rebuild/search paths.
- E2E coffee-machine fixture queries, including `"蒸汽很小"`.

Tests should avoid network access by default. Heavy model tests should be opt-in or use fixtures/mocks unless the task explicitly requires real model verification.

---

## Code Review Checklist

- Does the change preserve the layer boundaries from `design.md`?
- Are config defaults centralized?
- Are API, CLI, and tests using the same data contracts?
- Are errors returned as `{code, message, detail}`?
- Are storage writes atomic?
- Does rebuild failure leave the old state intact?
- Are new files covered by unit or E2E tests proportional to risk?
- Did the implementation avoid scope creep from M1-M4?

---

## Common Mistakes

- Optimizing for future HA before M0 is correct.
- Baking default paths or thresholds into several modules.
- Passing a custom `--config` only to the CLI wrapper while serving a separately imported FastAPI app with import-time defaults. If `serve --config path.yaml` is supported, inject the loaded `Settings` into the API module before calling `uvicorn.run`.
- Putting blank optional numeric env vars into `.env.example` when the file is also used by `docker compose env_file`; empty strings do not parse as `int | None`.
- Testing only happy-path search while missing rebuild and storage failure paths.
- Treating `node_id` as stable across rebuilds.
- Forgetting that `implement.jsonl` and `check.jsonl` determine what future agents automatically load.
- Letting tests pass only because the developer workspace has optional extras or generated `.tmp/` reports. Tests for optional integrations should skip clearly when the extra is absent, and batch/CLI tests should create their own report fixtures instead of depending on local evaluation artifacts.
- Updating full rebuild diagnostics or derived artifacts while forgetting incremental rebuild. If full rebuild writes safe `GraphState.meta` summaries such as `pdf_quality`, `ocr`, or `assets`, or writes derived stores such as `asset_manifest.json`, incremental rebuild must either preserve the old data, add dirty-document deltas, or intentionally fall back to full. Otherwise the Manual Library and QA source-preview pages can lose PDF/OCR/source-preview status after a normal small upload even though the indexed text is correct.

## Scenario: Incremental Rebuild Derived Artifacts

### 1. Scope / Trigger

- Trigger: full rebuild and incremental rebuild both produce user-visible derived artifacts such as PDF quality summaries, OCR summaries, document asset manifests, or source preview readiness.

### 2. Signatures

- `build_kb(...) -> GraphState`
- `build_kb_incremental(...) -> IncrementalBuildResult`
- `GraphState.meta["assets"]`
- `GraphState.asset_manifest`

### 3. Contracts

- Full rebuild and successful incremental rebuild must both return a `GraphState` whose derived metadata and manifests are internally consistent.
- For document assets, incremental rebuild loads the existing manifest, updates assets for dirty active manuals, marks assets for removed/inactive dirty manuals as deleted, and preserves unchanged manuals' assets.
- `save_kb(...)` remains the single persistence path for `GraphState.asset_manifest`.
- User-facing APIs and pages must only receive safe asset URLs such as `/assets/{asset_id}?kb_name=...`; never expose storage keys, blob keys, local paths, checksums, or raw manifest rows.

### 4. Validation & Error Matrix

- Dirty active PDF with snapshots enabled -> extract/update that manual's page snapshot assets.
- Dirty active non-PDF -> replace that manual's assets with an empty set while preserving other manuals.
- Dirty disabled/deleted manual -> mark previous assets deleted or remove them according to the existing manifest operation.
- Renderer unavailable with non-strict assets -> preserve rebuild success and record failed asset records/summary.
- Asset extraction strict failure -> rebuild may fail or fall back according to the configured rebuild mode.

### 5. Good/Base/Bad Cases

- Good: upload PDF A, rebuild, upload PDF B incrementally, then QA source cards for both PDFs can open PNG previews.
- Base: upload TXT after a PDF; incremental rebuild preserves the PDF's existing preview assets.
- Bad: incremental rebuild updates chunks/vectors but returns `asset_manifest=None` or an assets summary containing only the latest dirty document.

### 6. Tests Required

- Unit: incremental rebuild after a persisted full rebuild preserves existing document assets and adds dirty PDF assets.
- Browser: real `/qa` flow over multiple real PDFs verifies source cards expose preview links and `/assets/...` returns PNG without storage/blob key leakage.
- Diagnostics: source preview readiness remains `ready` when at least one ready page snapshot exists after incremental rebuild.

### 7. Wrong vs Correct

#### Wrong

```python
return GraphState(graph=graph, vectors=vectors, meta=meta)
```

#### Correct

```python
meta["assets"] = asset_inventory_summary(asset_manifest, asset_summary)
return GraphState(graph=graph, vectors=vectors, meta=meta, asset_manifest=asset_manifest)
```

## Scenario: HTTP Embedding Provider

### 1. Scope / Trigger

- Trigger: embedding provider can be local, hashing, or OpenAI-compatible HTTP.

### 2. Signatures

- `create_embedder(model_name, device, batch_size, dim, provider, base_url, embeddings_url, api_key_env, timeout_seconds, dimensions, normalize)`
- `HttpEmbedder.encode_batch(texts: Sequence[str]) -> np.ndarray`
- `HttpEmbedder.encode_query(text: str) -> np.ndarray`

### 3. Contracts

- Config keys live under `model.*`: `provider`, `name`, `dim`, `batch_size`, `base_url`, `embeddings_url`, `api_key_env`, `timeout_seconds`, `dimensions`, `normalize`.
- `provider=http` sends `POST {base_url.rstrip("/")}/embeddings` unless `embeddings_url` is set.
- Request body includes `model`, `input`, `encoding_format="float"`, and optional `dimensions`.
- API key is read only from `os.environ[api_key_env]`; never store secret values in YAML or logs.
- Response must contain `data[].embedding`; sort by `data[].index` when present.
- Returned vectors are `np.float32` and normalized by default to preserve dot-product-as-cosine semantics.

### 4. Validation & Error Matrix

- Missing API key env -> `INVALID_CONFIG`.
- HTTP status error -> `EMBEDDING_FAILED` with status code and endpoint.
- Network/timeout/invalid JSON -> `EMBEDDING_FAILED`.
- Missing or malformed response vectors -> `EMBEDDING_FAILED`.

### 5. Good/Base/Bad Cases

- Good: SiliconFlow-compatible config uses `base_url=https://api.siliconflow.cn/v1` and `api_key_env=SILICONFLOW_API_KEY`.
- Base: local provider remains default for offline deployment.
- Bad: passing raw API keys in `config.yaml` or logging request headers.

### 6. Tests Required

- Payload shape includes `model`, `input`, `encoding_format`, optional `dimensions`, and Bearer header.
- Full `embeddings_url` overrides `base_url`.
- Missing API key and HTTP errors map to project errors.
- Env override test for `TAGMEMORAG__MODEL__PROVIDER=http`.

### 7. Wrong vs Correct

#### Wrong

```yaml
model:
  provider: http
  api_key: sk-...
```

#### Correct

```yaml
model:
  provider: http
  api_key_env: SILICONFLOW_API_KEY
```

## Scenario: Tesseract CLI OCR Provider

### 1. Scope / Trigger

- Trigger: enabling local OCR for PDF pages where native text extraction returns no useful text.

### 2. Signatures

- `OCRConfig.provider: "deterministic" | "tesseract_cli"`
- `OCRConfig.tesseract_command: str`
- `OCRConfig.pdf_renderer_command: str`
- `OCRConfig.language: str`
- `OCRConfig.dpi: int`
- `OCRConfig.timeout_seconds: float`
- `TesseractCliOCRProvider.recognize_pdf_page(context: OCRPageContext) -> OCRPageResult`

### 3. Contracts

- OCR remains default-off (`Settings.ocr.enabled=False`).
- `tesseract_cli` uses operator-installed system commands; it does not add Python OCR dependencies.
- The provider renders only `context.page_number` with `pdftoppm -f N -l N -r <dpi> -png`.
- The provider runs `tesseract <image> stdout -l <language>`.
- Command execution must use `subprocess.run(..., shell=False, capture_output=True, timeout=...)`.
- Returned OCR text enters the existing OCR chunk path; OCR is not a parallel retriever.

### 4. Validation & Error Matrix

- Missing renderer/OCR command -> `RuntimeError("ocr_command_missing:<binary>")`.
- Renderer/OCR timeout -> `RuntimeError("ocr_command_timeout:<stage>")`.
- Renderer/OCR non-zero exit -> `RuntimeError("ocr_command_failed:<stage>")`.
- Render command produces no image -> `RuntimeError("ocr_render_missing_output")`.
- `config validate` with `ocr.enabled=true` and `ocr.provider=tesseract_cli` checks command availability via `shutil.which` and reports `system_command` checks without running OCR.

### 5. Good/Base/Bad Cases

- Good: scanned page has no native text, renderer and Tesseract are installed, OCR text becomes a normal `pdf_ocr:<profile>` chunk.
- Base: OCR remains disabled and deterministic tests still run without system OCR tools.
- Bad: invoking OCR through `shell=True`, logging raw OCR stderr/text, or requiring Tesseract in CI.

### 6. Tests Required

- Config parses `tesseract_cli` settings.
- Provider factory returns `TesseractCliOCRProvider`.
- Unit tests mock command execution and verify exact command shape, one-page render, stdout text return, missing-command failure, and parser failure summarization.
- Config validation tests mock `shutil.which` for renderer/OCR availability.

### 7. Wrong vs Correct

#### Wrong

```python
subprocess.run(f"tesseract {image} stdout -l {language}", shell=True)
```

#### Correct

```python
subprocess.run(["tesseract", str(image), "stdout", "-l", language], shell=False, capture_output=True, timeout=timeout)
```

## Scenario: HTTP Embedding Large Batch Failure Hardening

### 1. Scope / Trigger

- Trigger: HTTP embedding providers may reject or time out on larger PDF-derived batches even when single-query readiness probes pass.

### 2. Signatures

- `HttpEmbedder.encode_batch(texts: Sequence[str]) -> np.ndarray`
- `HttpEmbedder._request_batch_with_split(texts: Sequence[str]) -> np.ndarray`
- `HttpEmbedder._failure_detail(texts, split_attempted, status_code=None, error_type=None) -> dict[str, object]`

### 3. Contracts

- `model.batch_size` is the maximum HTTP embedding request size, not a guarantee that every provider accepts that request.
- A failed multi-item HTTP embedding request must be retried by splitting into smaller sub-batches before surfacing a final failure.
- Successful split retries must preserve input order and existing normalization behavior.
- Failure detail may include endpoint, status/error type, batch size, min/max text length, total text length, and split-attempt status.
- Failure detail must not include raw document text, request body, Authorization headers, API keys, provider response body, vectors, source paths, or snippets.

### 4. Validation & Error Matrix

- HTTP status failure on multi-item batch -> split retry; if sub-batches pass, return vectors.
- HTTP status failure on single-item batch -> `EMBEDDING_FAILED` with sanitized detail.
- Network/timeout/invalid JSON on multi-item batch -> split retry; if sub-batches fail, surface sanitized final detail.
- Vector count/shape/content validation failures -> `EMBEDDING_FAILED` as before.

### 5. Good/Base/Bad Cases

- Good: 32-item request fails, two 16-item requests pass, rebuild continues with vectors in original order.
- Base: configured batch succeeds on first request; no fallback is visible to callers.
- Bad: error detail includes provider body or raw PDF text to help debugging.

### 6. Tests Required

- Multi-item batch failure falls back to smaller HTTP calls and preserves vector order.
- Final failure detail contains safe numeric diagnostics and no raw text or secret values.
- Existing payload, endpoint override, dotenv key, missing key, and provider factory tests remain green.

### 7. Wrong vs Correct

#### Wrong

```python
detail = {"endpoint": endpoint, "body": provider_error_body, "input": texts}
```

#### Correct

```python
detail = {
    "endpoint": endpoint,
    "batch_size": len(texts),
    "max_text_chars": max(len(text) for text in texts),
    "split_attempted": True,
}
```

## Scenario: Qdrant Large Vector Upsert Hardening

### 1. Scope / Trigger

- Trigger: Qdrant-backed rebuilds can exceed the server HTTP JSON payload limit when one upsert contains hundreds of high-dimensional vectors.

### 2. Signatures

- `QdrantVectorStore.update(ids: np.ndarray, vecs: np.ndarray, payloads: list[dict[str, Any]] | None = None) -> None`
- `QdrantVectorStore.add(ids: np.ndarray, vecs: np.ndarray, payloads: list[dict[str, Any]] | None = None) -> None`

### 3. Contracts

- Qdrant vector writes must be split into bounded upsert calls while preserving node id order and payload alignment.
- Dimension checks, id/vector count checks, and payload count checks run before any upsert batch is sent.
- Payloads must continue through `_safe_payload`; raw chunk text and vectors must not be stored as Qdrant payload fields.
- Batch sizing is an implementation limit, not user-facing config, unless a future task proves operators need a setting.

### 4. Validation & Error Matrix

- Oversized vector set -> multiple upsert calls; rebuild can continue if all batches succeed.
- Any batch failure -> `STORAGE_LOAD_FAILED` with collection and safe provider error detail; active graph remains unchanged.
- Payload count mismatch -> `STORAGE_SCHEMA_MISMATCH` before writing.
- Vector dimension mismatch -> `STORAGE_SCHEMA_MISMATCH` before writing.

### 5. Good/Base/Bad Cases

- Good: 423 vectors with 4096 dimensions are written as several smaller Qdrant upserts.
- Base: small vector sets still write successfully; callers do not need to know batching occurred.
- Bad: increasing Qdrant server request limits is the only fix, or storing fewer payload safety fields to squeeze under the limit.

### 6. Tests Required

- Unit test proves a large `QdrantVectorStore.update` call is split into ordered upsert batches.
- Existing Qdrant save/load, inspect, and incremental sync tests remain green.
- Real-provider pilot should inspect Qdrant point count and missing-vector count after rebuild.

### 7. Wrong vs Correct

#### Wrong

```python
client.upsert(collection_name=collection, points=all_points)
```

#### Correct

```python
for batch in batches:
    client.upsert(collection_name=collection, points=batch)
```

## Scenario: Answer Citation Compliance

### 1. Scope / Trigger

- Trigger: OpenAI-compatible answer providers may return citation ids in generated answer text instead of structured `message.citations`.

### 2. Signatures

- `build_answer_prompt(question, retrieve_payload, prompt_version) -> AnswerPrompt`
- `OpenAICompatibleAnswerGenerator.generate(context: AnswerRequestContext) -> AnswerGeneration`
- `validate_generation_citations(generation, allowed_citation_ids) -> AnswerGeneration`

### 3. Contracts

- The answer prompt must tell providers to use exact `citation_id` values in square brackets, e.g. `[cit_001]`.
- OpenAI-compatible parsing may extract bracketed `cit_*` ids from answer text.
- Extracted ids are candidates only; `validate_generation_citations` must still drop any id not present in `AnswerPrompt.allowed_citation_ids`.
- Provider profiles for reasoning-style answer models may set a larger `answer.max_output_tokens` than the global default; the production-provider DeepSeek profile uses 1024.
- Committed reports and logs must not include raw generated answer text, raw retrieval snippets, provider bodies, or secrets.

### 4. Validation & Error Matrix

- Provider returns structured citations -> keep them if allowlisted.
- Provider returns bracketed text citations -> extract them, then validate against the allowlist.
- Provider returns invented citation ids -> drop them and emit `answer_dropped_invalid_citations`.
- Provider returns empty content -> `AnswerGenerationError`, degraded by `/answer` as `answer.kind=error`.

### 5. Good/Base/Bad Cases

- Good: answer text contains `[cit_001]`; retrieve allowed ids include `cit_001`; final answer citations include `cit_001`.
- Base: provider returns no citations; answer may still be non-empty but citation count is zero and remains a quality gap.
- Bad: accepting arbitrary bracketed ids without checking the retrieve allowlist.

### 6. Tests Required

- Prompt test asserts square-bracket citation instructions are present.
- OpenAI-compatible parser test extracts citation ids from text-only responses.
- Validation test drops unknown text-extracted ids.
- Profile config test guards DeepSeek-safe answer budget.

### 7. Wrong vs Correct

#### Wrong

```python
citations = [AnswerCitation(cid) for cid in re.findall(r"\\[(.*?)\\]", text)]
```

#### Correct

```python
generation = parse_provider_response(data)
generation = validate_generation_citations(generation, prompt.allowed_citation_ids)
```

## Scenario: Answer Intent and Local Formatting

### 1. Scope / Trigger

- Trigger: changing local answer wording, deterministic noop answer formatting,
  or rule-based answer intent classification.

### 2. Signatures

- `classify_answer_intent(question) -> AnswerIntent`
- `NoopAnswerGenerator.generate(context: AnswerRequestContext) -> AnswerGeneration`

### 3. Contracts

- Rule-based answer intent classification belongs in the answer layer, not in
  FastAPI route handlers, CLI commands, or general request orchestration.
- Product-manual troubleshooting and safety questions may use action-oriented
  prefixes such as `建议先这样处理：` and `建议先保证安全：`.
- Generic documentation/software/web questions such as GitHub workflow, pull
  request, repository, README, API, and tutorial questions must use neutral
  documentation framing such as `根据资料可确认：`.
- Unsupported part-number, disassembly, or replacement questions keep the
  insufficient-evidence framing even when retrieved evidence contains adjacent
  maintenance content.
- English keyword matching for short documentation terms must be word-boundary
  aware so terms such as `api` do not match unrelated words such as `rapid`.
- New answer-formatting heuristics should be covered by focused answer-layer
  tests and should not add more branches to `api.py` or `cli.py`.

### 4. Validation & Error Matrix

- Generic software documentation question with multiple evidence items -> uses
  neutral documentation framing.
- Product troubleshooting question with multiple evidence items -> uses
  action-oriented step framing.
- Safety question with matching safety evidence -> safety framing takes
  precedence.
- Unsupported repair/replacement question -> insufficient-evidence repair
  framing takes precedence.

### 5. Good/Base/Bad Cases

- Good: a GitHub pull request workflow answer starts with `根据资料可确认：`.
- Good: a weak-steam product answer starts with `建议先这样处理：`.
- Bad: adding another route-local or CLI-local keyword list to decide answer
  wording.

### 6. Tests Required

- Answer generator tests for generic documentation vs troubleshooting prefix
  boundaries.
- Intent tests for short-token false positives.
- Existing safety and unsupported-repair answer tests remain green.

## Scenario: Answer-Quality Diagnostics Command

### 1. Scope / Trigger

- Trigger: answer-quality diagnostics run from the eval CLI and produce a
  bounded report for groundedness, relevance, citation support, and refusal
  behavior.

### 2. Signatures

- CLI:
  `python -m tagmemorag eval answer-quality --suite <jsonl> [--output <json>]`
- Backend:
  `load_answer_quality_suite(path) -> list[AnswerQualityCase]`
- Backend:
  `run_answer_quality_diagnostics(suite_path) -> AnswerQualityReport`
- Backend:
  `evaluate_answer_quality_case(case) -> AnswerQualityCaseResult`

### 3. Contracts

- Suite rows are JSONL objects with `id`, `question`, `answer`, `contexts`,
  and `expected`.
- `contexts` entries include `citation_id` and may include authored fixture
  text/source.
- `expected` booleans cover `grounded`, optional `relevant`, optional
  `citation_supported`, and optional `refusal_expected`.
- Reports use schema version `answer_quality.v1`.
- Default report output includes case ids, expected/observed booleans, scores,
  bounded failures, bounded warnings, and summary counts.
- Default reports must not include full context snippets, provider responses,
  secrets, stack traces, or runtime document chunks.
- The default judge is deterministic and local. Live/provider-backed judges
  must be explicit, env-gated, and skipped safely when env is absent.

### 4. Validation & Error Matrix

- Missing suite path or unreadable suite -> `EvalSuiteError`, CLI exit `2`.
- Invalid JSONL row -> `EvalSuiteError` with line number, CLI exit `2`.
- Duplicate case id -> `EvalSuiteError`, CLI exit `2`.
- Missing required case fields -> `EvalSuiteError`, CLI exit `2`.
- Diagnostics pass -> CLI exit `0`.
- Diagnostics fail expected labels -> CLI exit `1` with bounded failure lines.

### 5. Good/Base/Bad Cases

- Good: a grounded answer cites an existing citation id and support markers
  match authored context.
- Base: an ungrounded fixture expects `grounded=false`; observing unsupported
  evidence is a passing diagnostic case.
- Bad: report JSON includes the full retrieved context, provider response
  body, API key env value, or runtime KB chunk text.

### 6. Tests Required

- Loader accepts valid fixtures and rejects duplicate/malformed rows.
- Grounded fixture passes with `grounded=true`.
- Ungrounded fixture passes when expected as `grounded=false`.
- Unknown citation produces a bounded warning and failure when support is
  expected.
- Report serialization omits context snippets.
- CLI writes a report and returns `0` for passing suites.
- Existing `/answer` and ranking eval tests remain green.

### 7. Wrong vs Correct

#### Wrong

```json
{
  "id": "case-1",
  "context": "full retrieved manual text...",
  "provider_response": {"raw": "..."}
}
```

#### Correct

```json
{
  "id": "case-1",
  "passed": false,
  "observed": {"grounded": false},
  "failures": ["grounded expected True observed False"]
}
```

## Scenario: Answer Prompt Context Quality

### 1. Scope / Trigger

- Trigger: changing answer prompt wording or the retrieval context passed into
  answer generation.

### 2. Signatures

- `SYSTEM_PROMPT`
- `build_answer_prompt(question, retrieve_payload, prompt_version) -> AnswerPrompt`
- `validate_generation_citations(generation, allowed_citation_ids) -> AnswerGeneration`
- `run_answer_quality_diagnostics(suite_path) -> AnswerQualityReport`

### 3. Contracts

- Retrieved context stays in the user message as untrusted source data.
- The system prompt must require exact square-bracket citation ids after
  evidence-backed claims.
- The system prompt must say to cite only context items that directly support a
  claim.
- The system prompt must tell providers to acknowledge conflicting context
  items and cite the relevant items.
- The system prompt must tell providers to say evidence is insufficient and not
  guess when context is insufficient.
- Prompt/context quality changes must be bounded to prompt text, context
  packing, fixtures, or tests unless a task explicitly changes answer schemas.
- Answer-quality reports must remain bounded and omit full context snippets and
  generated answer text.
- Live provider verification is optional; when used it must be explicit,
  env-gated, and safe to skip when env is absent.

### 4. Validation & Error Matrix

- Supported claim without citation -> answer-quality diagnostic observes
  `citation_supported=false`.
- Unsupported answer that cites an existing context id -> diagnostic observes
  `grounded=false` even when `citation_supported=true`.
- Conflicting evidence -> prompt must instruct the provider to name the
  conflict instead of choosing an unsupported answer.
- Insufficient evidence -> prompt must instruct refusal rather than guessing.

### 5. Good/Base/Bad Cases

- Good: answer cites `[cit_001]` only for a claim directly supported by
  `cit_001`, and says when other context conflicts.
- Base: offline deterministic diagnostics cover citation miss and conflicting
  evidence without requiring live LLM calls.
- Bad: prompt wording encourages citations as decoration, or diagnostics only
  check that some allowlisted citation id appears.

### 6. Tests Required

- Prompt test asserts direct-support, conflict, and no-guess instructions.
- Answer-quality fixtures include citation-miss and conflicting-evidence cases.
- Answer-quality report test proves failure/report output remains bounded.
- Existing `/answer` API and answer generator tests remain green.

### 7. Wrong vs Correct

#### Wrong

```python
SYSTEM_PROMPT = "Answer using the context and cite sources when useful."
```

#### Correct

```python
SYSTEM_PROMPT = (
    "Only cite a context item when it directly supports the claim. "
    "If context items conflict, say what is conflicting and cite the relevant items. "
    "If the context is insufficient, say that the available evidence is insufficient and do not guess."
)
```

## Scenario: LangChain Retriever and Tool Adapters

### 1. Scope / Trigger

- Trigger: exposing TagMemoRAG retrieval or agent tools through LangChain
  adapter objects.

### 2. Signatures

- Retriever:
  `TagMemoRAGRetriever(state, settings, embedder, config=None)`
- Retriever:
  `TagMemoRAGRetriever.retrieve(query, **kwargs) -> dict`
- Retriever:
  `TagMemoRAGRetriever.get_relevant_documents(query, **kwargs) -> list[Document]`
- Helper:
  `run_native_retrieve(request, state, settings, embedder, trace_id=None) -> dict`
- Helper:
  `retrieve_payload_to_documents(payload) -> list[Document]`
- Tools:
  `registry_to_langchain_tools(registry, ctx) -> list[StructuredTool]`

### 3. Contracts

- LangChain imports must be lazy. `import tagmemorag.langchain_adapter` must
  work without the optional `langchain` extra.
- Missing LangChain packages raise `LangChainAdapterUnavailable` with a clear
  optional-extra message.
- Retriever adapter calls must delegate to native TagMemoRAG retrieval rather
  than reimplementing search, evidence, QueryPlan, or PlanLog logic.
- Adapter-backed retrieve calls must write QueryPlan rows when persistence is
  enabled and respect private-KB persistence rules.
- LangChain `Document.metadata` may include low-sensitive fields such as
  `source_file`, `header`, `score`, `chunk_id`, `citation_id`, `plan_id`,
  `build_id`, and `kb_name`.
- Document metadata must not include raw query text, full provider responses,
  secrets, vectors, or unbounded runtime chunks beyond `page_content`.
- Tool wrappers delegate to `AgentToolRegistry` tools and keep registry
  behavior unchanged.

### 4. Validation & Error Matrix

- Missing LangChain document/tool classes -> `LangChainAdapterUnavailable`.
- Adapter-backed retrieve on public KB -> plan row exists and replay loader can
  read it.
- Adapter-backed retrieve on private KB -> plan id may be returned, but no
  persisted plan row is required.
- Native retrieval failure -> surface the same project exception as native
  retrieval; do not translate into LangChain-specific errors.

### 5. Good/Base/Bad Cases

- Good: a LangChain retriever call returns `Document` objects and creates a
  replayable QueryPlan row.
- Base: code using only native parser/retrieval imports without LangChain
  installed.
- Bad: importing the adapter package imports FastAPI/API globals at module load
  and creates a circular import through parser/manual-library code.

### 6. Tests Required

- Existing loader/splitter adapter tests still pass without LangChain.
- Retriever adapter writes a QueryPlan row and `ReplayPlanLoader` can read it.
- Tool wrapper missing-extra path raises `LangChainAdapterUnavailable`.
- Agentic tool registry tests stay green.
- Classic retrieval/eval tests stay green.

### 7. Wrong vs Correct

#### Wrong

```python
from tagmemorag.api import _retrieve_impl  # top-level adapter import
```

#### Correct

```python
def run_native_retrieve(...):
    from tagmemorag import api
    return api._retrieve_impl(...)
```

## Scenario: Agentic Production Tool Wiring

### 1. Scope / Trigger

- Trigger: wiring agentic retrieve/final tools to production retrieval and
  answer contracts.

### 2. Signatures

- Retrieve tool:
  `RetrieveTool(state, embedder, query_text, top_k, source_k, ...)`
- Final tool:
  `FinalTool(generator, context=None, question="", prompt_version=..., max_output_tokens=...)`
- Registry builder:
  `build_production_agent_tool_registry(state, embedder, answer_generator, reranker_dispatcher, query_text, config)`

### 3. Contracts

- Agentic production wiring remains default-off through `Settings.agentic.mode`.
- `RetrieveTool` must encode the runtime tool query on every call; it must not
  reuse a query vector captured at construction time.
- `FinalTool` may accept a fixed `AnswerRequestContext` for tests, but
  production mode should build context from the latest retrieve observation in
  `ctx.history`.
- `FinalTool` must call `build_answer_prompt` and
  `validate_generation_citations` before returning the answer payload.
- Agentic production tools append normal `plan_steps`; they do not write a
  second QueryPlan row per tool call.
- Package `__init__` files must stay lightweight. Do not import production
  builders from `agentic.tools.__init__` if that pulls in `search_runtime`,
  `state`, parser, or manual-library modules at package import time.

### 4. Validation & Error Matrix

- Runtime retrieve query differs after rewrite -> embedder receives the
  rewritten query.
- Generated answer includes unknown citation -> final tool drops it and emits
  `answer_dropped_invalid_citations`.
- Production registry run -> `plan_steps` contain retrieve/grade/final and
  latest retrieve context reaches the answer prompt.
- Private KB / budget exhaustion -> existing fallback behavior remains.
- Circular import during `import tagmemorag.agentic` or eval collection ->
  reject the change and move heavy imports behind direct module imports.

### 5. Good/Base/Bad Cases

- Good: `run_agent` with production tools retrieves evidence, grades, builds a
  prompt from that evidence, validates citations, and persists steps.
- Base: classic mode remains unchanged and `Settings().agentic.mode ==
  "classic"`.
- Bad: `RetrieveTool` embeds the original user query once and then ignores
  rewritten queries.

### 6. Tests Required

- Unit test proving retrieve embeds each runtime query.
- Unit test proving final builds context from latest retrieve and validates
  citations.
- Driver test proving production registry persists retrieve/grade/final steps.
- Existing budget/private-KB fallback tests remain green.
- Agentic eval slice names remain documented gates.

### 7. Wrong vs Correct

#### Wrong

```python
tool = RetrieveTool(state=state, query_vec=embedder.encode_query(initial), ...)
```

#### Correct

```python
tool = RetrieveTool(state=state, embedder=embedder, ...)
observation = tool({"query": rewritten_query}, ctx)
```

## Scenario: Production Pilot Command

### 1. Scope / Trigger

- Trigger: adding or changing `tagmemorag pilot run`, the operator-facing pre-pilot gate that composes config validation, provider probe, readiness smoke, and eval.
- This is a cross-layer CLI/service/report contract. Keep the CLI thin and put report assembly in `src/tagmemorag/production_pilot.py`.

### 2. Signatures

- CLI: `python -m tagmemorag pilot run --config <path> --suite <jsonl> --docs <dir> --workdir <dir> --output <path> --format json|markdown`
- Service: `run_production_pilot(config_path, suite_path, docs_path, workdir, top_k, source_k, thresholds) -> ProductionPilotReport`
- Writer: `write_pilot_report(report, path, fmt="json"|"markdown") -> None`

### 3. Contracts

- Response schema version: `production_pilot.v1`.
- Report fields: `status`, `config_path`, `suite_path`, `docs_path`, `workdir`, `stages`, `next_steps`.
- Stage fields: `name`, `status`, `detail`, optional `error`.
- Allowed detail content: stage counts, provider/check names, profile names, numeric eval metrics, eval suite filename, failed case ids.
- Forbidden detail content: raw eval queries, retrieved snippets, vectors, full source-file lists, API keys, Authorization headers, raw provider responses, generated answer text.
- Default local pilot thresholds may be lower than strict `eval run` defaults when documented as pilot-specific; strict regression gating should use `eval run --baseline`.

### 4. Validation & Error Matrix

- `config_validate.status == failed` -> pilot status `failed`.
- `provider_probe.status == failed` -> pilot status `failed`.
- `provider_probe.status == skipped` -> allowed for local/offline profiles.
- `readiness_smoke.status != passed` -> pilot status `failed`.
- `eval.summary.passed is false` -> pilot status `failed`.
- Runtime exceptions that prevent report creation -> CLI prints `pilot error: <type>: <reason>` to stderr and exits `2`.

### 5. Good/Base/Bad Cases

- Good: local hashing/NPZ pilot exits `0`, provider stage is all skipped, readiness and eval pass, and JSON/Markdown report is retained.
- Base: warning config checks produce pilot `warning` unless a later required stage fails.
- Bad: dumping `EvalReport.to_dict()` into the pilot report leaks queries and snippets; summarize only `summary.metrics`, counts, and failed case ids.

### 6. Tests Required

- Real local pilot test with hashing config and fixture data.
- Sanitization assertions that fixture queries/snippets and `actual_top_k` do not appear in the pilot report JSON.
- CLI tests for JSON file output, Markdown stdout, and failed report exit code.
- Failure aggregation test using intentionally strict thresholds.

### 7. Wrong vs Correct

#### Wrong

```python
stage_detail = eval_report.to_dict()
```

#### Correct

```python
stage_detail = {
    "cases": eval_report.summary.cases,
    "metrics": eval_report.summary.metrics.to_dict(),
    "failed_cases": [case.id for case in eval_report.cases if not case.passed],
}
```
