# PyMuPDF optional install design

## Scope

This task changes installation and operator guidance only. It does not alter the asset manifest schema, the `/assets/{asset_id}` route, or the default-off PDF page snapshot behavior.

## Dependency model

PyMuPDF remains optional because source previews are a verification enhancement. The base install must continue to support RAG search and Q&A without it. A dedicated optional extra lets operators opt in when they want clickable PDF page previews from QA source cards.

## Config validation

When `assets.enabled=true` and `assets.pdf_page_snapshots_enabled=true`, `config validate` checks whether module `fitz` is importable. If not, the dependency check should remain a warning and include a safe install command. It must not include local Python paths or environment-specific internals.

## Compatibility

Existing missing-renderer fallback behavior stays unchanged: rebuild degrades, diagnostics explain the missing renderer, and Q&A remains usable.
