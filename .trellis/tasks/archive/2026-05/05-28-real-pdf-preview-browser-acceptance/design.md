# Real PDF preview browser acceptance design

## Scope

This task is primarily acceptance validation. Code changes should be driven only by issues found during real use.

## Real flow

1. Install `pdf-preview` optional dependencies.
2. Start the app with `assets.enabled=true`, `assets.pdf_page_snapshots_enabled=true`, and answer generation enabled.
3. Upload a real PDF from `product_manuals/` through Manual Library.
4. Rebuild and inspect diagnostics for ready source previews.
5. Ask a question on `/qa`.
6. Click a citation and open the source preview URL.
7. Confirm the response is `image/png` and the UI does not expose storage keys or paths.

## Constraints

Do not commit generated asset files, uploaded runtime documents, or downloaded third-party bodies. Runtime validation output belongs under `.tmp/`.
