# Public docs site redesign

## Goal

Turn the public TagMemoRAG website into an official documentation-style site inspired by the Trellis docs structure: top utility bar, left grouped navigation, central documentation content, and right page outline.

## Requirements

- Replace the current marketing-style single-page layout with a docs-oriented layout.
- Use Chinese-first documentation copy suitable for public visitors.
- Keep it static and GitHub Pages friendly with no build step.
- Preserve links to GitHub and v0.1.0 release.
- Cover project overview, quick start, manual library, user Q&A, readiness, OCR, access, deployment, and FAQ.
- Do not expose secrets, local paths, storage keys, blob keys, checksums, or private runtime data.
- Update public-site tests for the new official-docs structure.

## Acceptance Criteria

- [ ] Site visually presents as official documentation rather than a marketing landing page.
- [ ] Left navigation groups and right page outline are present.
- [ ] Main content includes quick start and operator guide sections.
- [ ] Existing public site tests pass after being updated.
- [ ] Site can still be served as static files from `site/`.
