# Public web knowledge sampler

## Goal

Add a small, reproducible way to sample public web knowledge sources into the
existing TagMemoRAG build/eval pipeline. This is the first implementation step
after deciding that product manuals are only one validation domain for a more
general robust RAG system.

The sampler should fetch one or more public HTTP(S) pages, convert the visible
HTML text into Markdown, write sidecar metadata, and report what was
materialized. The first slice should avoid committing fetched third-party
content; callers choose an output directory such as `.tmp/general-web-samples`.

## Confirmed Facts

- Existing connector materialization writes Markdown plus sidecar metadata and
  can already feed `build_kb`.
- Connector contracts still expose manual-shaped fields (`manual_id`,
  `product_category`), but metadata is mirrored into generic document fields at
  build time.
- Default project dependencies do not include BeautifulSoup/html2text; the first
  sampler should use standard-library HTML parsing to avoid a new mandatory
  dependency.
- Current public benchmark direction includes software docs, policy/government
  documents, health/public information, help-center/FAQ pages, and product
  manuals.

## Requirements

- Provide a CLI command for public web sampling under a general namespace, not
  under `manualslib`.
- Support multiple `--url` values in one invocation.
- Support `--output-dir`, `--kb`, `--domain`, `--doc-type`, `--tag`,
  `--timeout-seconds`, and `--preview`.
- Fetch only `http://` or `https://` URLs.
- Convert HTML into deterministic Markdown with title and readable text blocks.
- Materialize fetched content as `.md` files plus sidecar metadata compatible
  with the existing build path.
- In preview mode, fetch and parse pages but do not write document content.
- Keep failure reports bounded and avoid echoing full fetched content.
- Do not add a new runtime dependency for this slice.

## Acceptance Criteria

- [ ] Unit tests cover HTML title/body extraction, safe slug generation, and
      bounded failures for invalid URLs.
- [ ] CLI tests prove preview mode and materialize mode wire arguments and
      produce structured JSON.
- [ ] Materialized output can be used by the existing build/eval pipeline.
- [ ] Existing connector/manualslib eval tests remain green where relevant.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
