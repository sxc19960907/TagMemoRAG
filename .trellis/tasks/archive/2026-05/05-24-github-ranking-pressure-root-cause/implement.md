# Implementation Plan

## Checklist

- [x] Create Trellis task and capture requirements.
- [x] Inspect retained ranking-pressure and general-web eval reports.
- [x] Inspect the GitHub Hello World source material and ranking implementation
      boundaries.
- [x] Start the task.
- [x] Record the root-cause diagnosis.
- [x] Run reproducible diagnostic commands.
- [ ] Commit and archive.

## Validation Commands

```text
.venv/bin/python scripts/diag_general_web_ranking_pressure.py \
  --report .tmp/eval/general-web-after-evidence-refinement.json \
  --format markdown \
  --output .tmp/eval/github-ranking-pressure-root-cause.md
```

```text
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/general_web.jsonl \
  --docs .tmp/general-web-eval/general_web \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web \
  --top-k 8 \
  --min-recall-at-k 0.0 \
  --min-mrr 0.0 \
  --min-hit-at-k 0.0 \
  --output .tmp/eval/github-ranking-pressure-general-web.json
```

## Rollback

This is a documentation/diagnostic task. If the diagnosis proves incorrect,
update or remove the task diagnosis before archiving; no runtime rollback should
be needed.
