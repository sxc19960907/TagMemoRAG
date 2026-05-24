# Design

## Boundary

Add a local, offline diagnostic report over existing `tagmemorag eval run`
outputs. The tool does not run eval, fetch web content, rebuild a KB, or change
ranking behavior.

## Input

An eval JSON report such as:

```text
.tmp/eval/general-web-after-evidence-prior.json
```

or the refreshed:

```text
.tmp/eval/general-web-after-evidence-refinement.json
```

The report already contains metrics and top-k result metadata. The diagnostic
uses only the stored fields.

## Classification

A case is a ranking-pressure item when:

- `hit_at_k > 0`
- `recall_at_k > 0`
- `mrr < 1.0`
- at least one expected result is matched, but the first matched rank is after
  rank 1

These cases are not top-k misses. They are candidates where ranking order, not
basic retrieval reachability, is the next quality surface.

## Output

JSON schema:

- `schema_version`
- `report_path`
- `suite`
- `summary`
- `items`

Each item includes:

- `case_id`, `kb_name`, `metrics`
- `first_matched_rank`
- `expected_count`, `matched_expected_indexes`
- `pressure_rank_count`
- `top_results`

Each top result is bounded:

- `rank`
- `matched_expected_indexes`
- `source_file`
- `header`
- cue counts:
  `definition_cues`, `overview_cues`, `action_cues`, `chrome_cues`
- `body_word_count`

The diagnostic intentionally omits raw query text and raw result text by
default. A future task can add an explicit opt-in flag if raw review is needed.

## Compatibility

Keep the implementation in `scripts/` like existing diagnostics. Unit tests can
import the script by adding `scripts/` to `sys.path`, matching existing test
patterns.
