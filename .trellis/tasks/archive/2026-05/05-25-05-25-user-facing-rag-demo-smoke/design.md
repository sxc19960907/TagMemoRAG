# User-facing RAG demo smoke path design

## Architecture and Boundaries

Add a small CLI surface under a new `demo` command group:

```text
python -m tagmemorag demo qa --config examples/config/qa-demo.yaml --kb default "蒸汽很小怎么办？"
```

The command is an entry-point orchestration layer only. It loads the configured KB, injects the loaded state/embedder/settings into the existing API module, constructs an `AnswerRequest`, and calls the same answer builder path used by `/answer`. It does not reimplement retrieval, QueryPlan persistence, evidence building, or answer generation.

## Data Flow

```text
qa-demo.yaml -> load_config -> create_embedder_from_config
             -> load_kb(default)
             -> api.answer(AnswerRequest)
             -> bounded CLI JSON response
```

The CLI response is a user-facing demo payload:

- `schema_version: demo_qa.v1`
- `status`
- `kb_name`, `build_id`, `plan_id`
- `question`
- `answer` summary with `kind`, `text`, `citations`, `citation_count`, `confidence`, `model_id`, `prompt_version`
- `retrieve` summary with `answerable`, `evidence_count`, `citation_count`, and bounded sources
- `warnings`

## Compatibility

- Existing `build`, `search`, API routes, readiness smoke, and eval commands remain unchanged.
- `answer.enabled` remains default-off globally; the demo config opts in with noop provider.
- The seed script keeps its current docs/config defaults but falls back to `.venv/bin/python` or `python3` if `uv` is unavailable.

## Privacy and Retention

The command prints the user-visible answer and bounded source metadata. It must not print vectors, provider request/response bodies, secrets, raw candidate lists, or debug token internals. If `--output` is used, it writes the same bounded payload only.

## Rollback

Rollback is limited to removing the new `demo` parser/dispatch branch, demo service module, seed-script fallback, README section, and focused tests. No persisted data migrations are introduced.
