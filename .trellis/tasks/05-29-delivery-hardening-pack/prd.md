# Delivery hardening pack

## Goal

Harden the project for a broader user-facing trial by improving three delivery surfaces together:

1. More realistic business-document black-box coverage.
2. Production deployment experience around backup, restore, permissions, monitoring, and release checks.
3. A more official-feeling public documentation site.

## User Value

A prospective user or operator should see credible evidence that TagMemoRAG works on real business manuals, understand how to deploy and operate it safely, and have a public docs site that feels like a product guide rather than a single landing page.

## Confirmed Facts

- The repo already contains real product-manual PDFs for washer, oven, refrigerator, and dryer categories under `product_manuals/`.
- Existing browser tests cover real washer/oven PDF source preview and real-provider QA when explicitly enabled.
- Existing production docs cover deployment profiles, config/secrets, persistence matrix, bundles, diagnostics, and production environment verification.
- The public docs site is static under `site/` and published by GitHub Pages.
- Current public-site tests assert the site has basic docs navigation, public release links, OCR/access/deployment sections, and no obvious secret/storage-key leakage.

## Requirements

### Real Business Document Black-Box Coverage

- Add or strengthen an opt-in browser black-box test over multiple real product PDF categories beyond the current washer/oven path.
- The test must verify a normal browser user can upload/index real PDFs, ask category-specific questions, inspect sources, and avoid cross-document contamination.
- The test must assert source cards do not expose internal storage or graph identifiers.
- If a category cannot produce a stable answer with the offline deterministic provider, document the boundary and keep the test focused on stable evidence.

### Production Deployment Experience

- Add a concise operator-facing release/deployment checklist that connects backup/restore, auth/permissions, monitoring, provider checks, and rollback into one flow.
- The checklist must point to existing deeper runbooks instead of duplicating every command.
- The checklist must preserve secret hygiene: no raw keys, no Authorization headers, no generated answer text, and no raw document snippets in retained artifacts.

### Public Documentation Site

- Make the static docs site feel more like official product documentation:
  - clearer information architecture,
  - stronger quick-start path,
  - deployment/operations section,
  - real-document support matrix,
  - release-readiness checklist,
  - clear links to deeper docs.
- Keep the site static and GitHub Pages compatible.
- Keep text and layout responsive with no horizontal overflow.

## Out Of Scope

- Adding a full docs framework or build step.
- Implementing durable distributed queues, HA, automatic backups, or multi-replica write coordination.
- Adding new production providers or changing provider defaults.
- Adding legacy `.doc` support.
- Running paid/live LLM provider checks unless already configured by environment.

## Acceptance Criteria

- [x] Real business-document browser coverage includes at least three product categories when local real PDFs are present.
- [x] Production release/deployment checklist is documented and linked from the public docs site.
- [x] Public docs site includes quick start, real-document support, operations, quality gates, and roadmap sections in a more official docs layout.
- [x] Public-site/documentation tests assert the new content and no secret/internal-key leakage.
- [x] Focused browser and docs tests pass.
- [x] Full local quality gate passes.
- [ ] Changes are committed, pushed, CI passes, and task is archived.

## Verification

- `uv run pytest tests/unit/test_public_site.py tests/unit/test_documentation_handoffs.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_real_product_pdf_source_preview_user_flow -q -s`
- Static public-site layout check with Playwright at `1440x980` and `390x844`, asserting no horizontal overflow.
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
