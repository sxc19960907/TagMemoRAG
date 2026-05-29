# Design

## Approach

This is a documentation, acceptance-test, and public-site hardening task. It should reuse existing system behavior and existing browser helpers rather than introducing new runtime architecture.

## Work Areas

### Browser Real-Document Acceptance

Extend the existing real-product PDF browser coverage to include at least three product categories from `product_manuals/`. The current washer/oven path already verifies source previews and source-card safety. The hardened path should add refrigerator or dryer coverage with a stable category-specific question and source assertion.

The test should stay opt-in with `TAGMEMORAG_RUN_BROWSER_UI=1` and skip cleanly when optional PDF snapshot renderer or local sample PDFs are absent.

### Production Checklist

Add a concise checklist document that links the existing detailed operations docs:

- `docs/production-deployment-operations.md`
- `docs/production-environment-verification.md`
- `docs/production-pilot-runbook.md`
- `docs/rag-quality-gates.md`

The checklist should organize the operator path into preflight, backup/restore, access, monitoring, release, rollback, and post-release evidence.

### Public Docs Site

Revise the static site content and visual hierarchy while keeping the current no-build GitHub Pages model. The site should behave like a documentation hub:

- topbar brand and external links,
- left navigation,
- searchable-looking but nonfunctional search affordance,
- sections for start, user guide, document support, operations, quality, and roadmap,
- concise tables/checklists.

No runtime JavaScript is required.

## Compatibility

- Keep existing URLs and GitHub Pages workflow.
- Keep tests deterministic and skip optional browser paths when prerequisites are missing.
- Do not commit runtime artifacts from `.tmp/`.

## Rollback

All changes should be limited to docs, static site assets, and tests. If the browser test exposes a product bug, fix it in a separate scoped patch within this task only if small; otherwise document it and create a follow-up task.
