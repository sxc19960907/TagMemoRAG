# Real Web Knowledge Eval Benchmark

## Goal

Build a broader, repeatable real-web knowledge evaluation slice so RAG quality work is validated against live public documentation instead of mostly synthetic snippets. The benchmark should exercise different knowledge shapes: software tutorials, workflow documentation, web platform reference/guidance, and consumer-facing help-center guidance.

## User Value

The system should be trustworthy as a general-purpose RAG engine, not only a product-manual QA demo. Real web documentation catches parser, ranking, metadata, context packing, and answer-quality issues that short hand-written fixtures miss.

## Confirmed Facts

- The project already has a `knowledge sample-web` importer that materializes public web pages into Markdown plus metadata sidecars.
- `scripts/seed_general_web_eval.sh` currently seeds Python Tutorial and GitHub Hello World docs into `.tmp/general-web-eval/general_web`.
- `tests/fixtures/eval/general_web.jsonl` and `scripts/diag_general_web_answer_eval.py` already run retrieval and answer-quality checks over that seeded corpus.
- The existing mixed-domain diagnostic reuses `.tmp/general-web-eval/general_web` alongside real PDFs from `product_manuals/`.
- Candidate real public sources checked on 2026-05-24:
  - Python Tutorial: official Python docs cover high-level data structures, object-oriented programming, standard library, modules, and source/binary distribution.
  - GitHub Hello World: official GitHub docs cover repositories, README/Markdown, branches, commits, pull requests, and merge flow.
  - MDN HTTP caching: MDN covers HTTP cache reuse, `Cache-Control`, `no-cache`, `no-store`, `private`, and common caching patterns.
  - Google Search Help: Google help docs cover exact/related term matching, `site:` search, minus-site exclusion, location/language/date/content-type relevance signals.

## Requirements

- Extend the real-web seed corpus with at least two additional public documentation/help pages from different domains beyond Python and GitHub.
- Add retrieval eval cases for the new real pages using text that is expected to appear in the materialized Markdown output, with source metadata constraints.
- Add answer-quality coverage for at least one newly added non-software-doc page through the existing live seeded retrieval diagnostic path.
- Keep third-party content out of the repository; only URLs, eval expectations, scripts, and docs should be committed.
- Keep the seeded corpus opt-in under `.tmp` because it depends on live public URLs.
- Prefer stable official documentation/help pages over blogs or news pages.

## Acceptance Criteria

- [ ] `scripts/seed_general_web_eval.sh` seeds at least four real public pages across at least three source domains.
- [ ] `tests/fixtures/eval/general_web.jsonl` includes real-web cases for the newly seeded domains.
- [ ] `scripts/diag_general_web_answer_eval.py` passes over the expanded seeded corpus.
- [ ] The mixed-domain diagnostic still passes after staging the expanded public-web corpus with `product_manuals/`.
- [ ] Unit tests cover seed script/source-list expectations without fetching the network.
- [ ] README and backend architecture docs explain that the general-web slice now spans multiple real document types/domains and remains opt-in.

## Out of Scope

- Do not commit fetched third-party page content.
- Do not introduce an external LLM judge.
- Do not tune retrieval algorithms in this task unless the expanded real-web cases reveal a small, clearly scoped compatibility issue.
- Do not add fragile news/current-event pages to the fixed benchmark.
