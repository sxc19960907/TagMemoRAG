# Real PDF QA user experience acceptance design

## Scope

This task is real user-flow validation with targeted fixes. It should avoid broad ranking rewrites unless the real flow exposes a clear, bounded defect.

## Real flow

1. Start the app with answer generation and PDF page snapshots enabled.
2. Upload at least two real local PDFs through Manual Library.
3. Rebuild and confirm source preview readiness.
4. Ask realistic questions from the QA page.
5. Inspect answer text, citation chips, source cards, page labels, and preview links.

## Safety boundaries

The user page must not expose debug IDs, storage keys, blob keys, local paths, checksums, raw manifests, or node ids. Runtime data created for validation stays under pytest temporary directories or `.tmp/` and is not committed.
