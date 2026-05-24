# Design

## Boundary

This task updates the committed retrieval eval fixture only. Runtime behavior,
ranking, parsing, context packing, and answer generation are unchanged.

## Fixture Semantics

`tests/fixtures/eval/general_web.jsonl` stores query-level relevant evidence.
Each `relevant` entry should represent an independently useful supporting chunk,
not one canonical exact sentence. This matches the architecture guidance that
multi-evidence questions should list every independently useful supporting
chunk as a separate relevant entry.

For this task, only the MDN `no-cache`/`private` case qualifies for refinement:

- Existing top-ranked chunks answer the private-cache / personalized-response
  part of the query but do not match the current exact expected strings.
- The combined `no-cache, private` directive chunk supports the query's
  no-cache/private/shared-cache relationship.
- The GitHub cases are not refined here because their higher-ranked chunks are
  broad overview/action text and should remain visible ranking pressure.

## Metric Impact

Adding matched top-k MDN evidence should:

- move the MDN case first relevant rank from 7 to 1
- increase MDN recall because the new entries are already in top-k
- keep suite hit@k at `1.0`
- preserve the fact that GitHub repository and pull-request cases still have low
  MRR and remain future ranking targets

## Validation

Use the existing seeded public-web docs and local hashing config to rerun
general-web retrieval. Run lightweight unit tests that exercise eval fixture
loading / CI exclusion so malformed JSONL or accidental default-CI inclusion is
caught.
