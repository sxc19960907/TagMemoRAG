# TagMemoRAG

TagMemoRAG is a browser-first RAG system for turning real product manuals and team documents into cited answers. It focuses on practical local trials today: upload documents, rebuild a knowledge base, ask questions in the browser, inspect sources, collect retrieval feedback, and run release-quality checks before handing the system to users.

- Public docs site: https://sxc19960907.github.io/TagMemoRAG/
- Repository: https://github.com/sxc19960907/TagMemoRAG
- Current release: https://github.com/sxc19960907/TagMemoRAG/releases/tag/v0.1.0
- Fast browser walkthrough: [docs/browser-rag-quick-start.md](docs/browser-rag-quick-start.md)

## Current Status

TagMemoRAG is pilot-ready / technical pre-production. The user-facing RAG path works in the browser with managed document upload, indexing, Q&A, citations, source cards, feedback, language switching, and operator readiness checks.

It is not yet a fully managed multi-tenant production platform. High availability, automated backup policy, production OCR provider choice, full SaaS connectors, and UI-level rollout controls are still planned work.

## What It Does

- Browser Q&A page for normal users, including first-run upload guidance.
- Admin RAG Workbench for readiness, retrieval inspection, feedback, and rebuild flow.
- Manual Library for document upload, metadata, rebuild state, diagnostics, and bundle import/export.
- Cited retrieval and answer generation through `/retrieve`, `/answer`, and the browser UI.
- Local deterministic demo profile that works without external API keys.
- Optional production-provider profile for Qdrant, S3-compatible storage, HTTP embeddings, reranking, and answer generation.
- Public static documentation site under `site/`, designed for GitHub Pages.

## Document Support

Browser uploads accept `.md`, `.txt`, and text-based `.pdf` manuals; uploads also accept `.docx` files when the document text is readable. Scanned PDFs can use the default-off OCR foundation when an OCR provider is configured; without OCR, image-only pages may not produce searchable text.

For the latest real-document verification notes, see [docs/real-pdf-document-intake-test-2026-05-27.md](docs/real-pdf-document-intake-test-2026-05-27.md).

## Install

Use `uv` from the repository root:

```bash
uv sync --extra dev
```

Or install into an existing virtual environment:

```bash
pip install -e ".[dev]"
```

Optional extras are installed only when needed:

```bash
uv sync --extra dev --extra qdrant --extra s3 --extra pdf-preview --extra langchain
```

## 5-Minute Browser Demo

Seed a local demo KB and verify one cited answer:

```bash
uv run python -m tagmemorag demo library-qa \
  --config examples/config/qa-demo.yaml \
  --output .tmp/tagmemorag-qa-demo/library-qa-response.json
```

Start the local server:

```bash
uv run python -m tagmemorag serve \
  --host 127.0.0.1 \
  --port 8000 \
  --config examples/config/qa-demo.yaml
```

Open the browser UI:

```text
http://127.0.0.1:8000/
```

Useful local pages:

- RAG Workbench: `http://127.0.0.1:8000/admin/rag-workbench?kb_name=default`
- Manual Library: `http://127.0.0.1:8000/admin/manual-library?kb_name=default`
- Ask Q&A: `http://127.0.0.1:8000/qa?kb_name=default`
- People & Access: `http://127.0.0.1:8000/admin/people?kb_name=default`

The demo config has auth disabled, so the API token field can stay empty. Try asking:

```text
蒸汽很小怎么办？
```

For the full browser-first flow, including upload, rebuild, navigation, and recovery hints, use [docs/browser-rag-quick-start.md](docs/browser-rag-quick-start.md).

## Operator Handoff

For a small local trial, start with [docs/trial-operator-handoff-2026-05-27.md](docs/trial-operator-handoff-2026-05-27.md). It points operators to the live browser pages, retained pilot reports, feedback triage, and safe recovery steps.

For CI and retained report boundaries, see [docs/trial-report-ci-handoff.md](docs/trial-report-ci-handoff.md). Default CI does not run the full browser QA readiness flow; GitHub Actions remains the authoritative post-push gate.

## Configuration

The shortest local browser profile is:

```text
examples/config/qa-demo.yaml
```

Production-like verification profiles live under `examples/config/` and are described in:

- [docs/mvp-delivery-guide.md](docs/mvp-delivery-guide.md)
- [docs/production-deployment-operations.md](docs/production-deployment-operations.md)
- [docs/production-environment-verification.md](docs/production-environment-verification.md)
- [docs/production-provider-smoke-runbook.md](docs/production-provider-smoke-runbook.md)

Keep provider credentials in your shell, local secret manager, deployment secret store, or CI secrets. Do not write secret values into YAML, docs, logs, shell history captures, or retained reports.

## Quality Checks

Run the focused public-site and documentation handoff checks:

```bash
uv run pytest tests/unit/test_public_site.py tests/unit/test_documentation_handoffs.py -q
```

Run the deterministic local readiness smoke:

```bash
uv run python -m tagmemorag readiness smoke
```

Run the standard unit suite when changing backend behavior:

```bash
uv run pytest tests/unit -q
```

The full quality gate matrix is documented in [docs/rag-quality-gates.md](docs/rag-quality-gates.md).

## API Surface

The browser is the primary user experience, but the service also exposes API endpoints for integrations and diagnostics:

- `POST /retrieve` returns evidence-aware retrieval results.
- `POST /answer` returns a cited answer when answer generation is enabled.
- `POST /search` remains available for compatibility and debugging.
- `POST /rebuild` rebuilds the active knowledge base.
- Manual-library, feedback, readiness, and admin endpoints back the browser UI.

Use the browser and docs first for normal operation; API details are intentionally kept out of this README so the project entrance stays readable.

## Public Docs Site

The static public site lives in [site/index.html](site/index.html) and [site/styles.css](site/styles.css). It is designed to be published through GitHub Pages with no build step.

Validate it locally with:

```bash
uv run pytest tests/unit/test_public_site.py -q
```

## Documentation Map

- Browser user path: [docs/browser-rag-quick-start.md](docs/browser-rag-quick-start.md)
- MVP handoff: [docs/mvp-delivery-guide.md](docs/mvp-delivery-guide.md)
- Production operations: [docs/production-deployment-operations.md](docs/production-deployment-operations.md)
- Production environment verification: [docs/production-environment-verification.md](docs/production-environment-verification.md)
- Quality gates: [docs/rag-quality-gates.md](docs/rag-quality-gates.md)
- Trial operator handoff: [docs/trial-operator-handoff-2026-05-27.md](docs/trial-operator-handoff-2026-05-27.md)
- CI handoff: [docs/trial-report-ci-handoff.md](docs/trial-report-ci-handoff.md)
- Tag ordering convention: [docs/tag-ordering-convention.md](docs/tag-ordering-convention.md)
- Historical WAVE architecture notes: [docs/wave-phase1-architecture.md](docs/wave-phase1-architecture.md)

## Development Notes

Runtime data belongs under `data/` or `.tmp/` and should not be committed. Project coding guidance lives under `.trellis/spec/`; active and archived Trellis tasks preserve design decisions that should not be copied back into the README unless they are user-facing.

Before release or push, run the smallest quality tier that covers the change and then check GitHub Actions after push.

## Roadmap

Near-term work is focused on making the browser experience easier to trust and operate:

- Production OCR provider wiring and clearer scanned-PDF guidance.
- Stronger release/publish automation and public docs coverage.
- More real-document black-box browser tests.
- Deployment hardening for backup, restore, observability, and operator rollback.
- Safer multi-user and multi-KB rollout controls.
