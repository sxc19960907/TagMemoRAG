# Design

## Boundary

This task adds a manifest-driven summary over existing retained reports. It does
not execute eval runs, fetch corpora, or change retrieval/ranking behavior.

## Manifest

The manifest is JSON so tests and future scripts can parse it without optional
dependencies. It contains:

- `schema_version`
- `slices[]`
  - `name`
  - `kind`
  - `suite_path`
  - `corpus_path` when a stable local corpus path exists
  - `rerun_command` when the slice is currently staged through an existing
    diagnostic script
  - `report_path`
  - `min_hit_at_k`
  - `min_recall_at_k`
  - `min_mrr`
- `gates[]`
  - `name`
  - `path`

## Summary

The package module reads only aggregate fields from report `summary` objects:
cases, passed, hit@k, recall@k, MRR, and gate status. Manifest corpus/rerun
fields are retained for the next automation child, but this task does not
execute them. The summary never copies case rows, queries, snippets, candidate
lists, or provider bodies.

Summary status is:

- `passed` when all slices and gates pass.
- `failed` when any required file is missing, malformed, below threshold, or a
  gate status is not `passed`.

## CLI

Add `scripts/default_on_retained_monitoring.py` with:

- `--manifest`
- `--output`
- `--format json|markdown`

The CLI returns exit code `0` for passed summaries and `1` for failed summaries.
