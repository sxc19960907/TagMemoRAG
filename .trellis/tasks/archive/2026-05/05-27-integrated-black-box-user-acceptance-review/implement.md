# Integrated Black Box User Acceptance Review Implementation Plan

## Checklist

- [x] Start the child task.
- [x] Read Trellis quality guidance.
- [x] Seed deterministic demo KB.
- [x] Start local server for browser review.
- [x] Perform in-app browser black-box QA review.
- [x] Fix blocking defects if found.
- [x] Run retained pilot/browser gates.
- [x] Write acceptance report and update parent progress.
- [x] Commit and archive the child task.

## Validation Commands

```bash
uv run python -m tagmemorag demo library-qa --config examples/config/qa-demo.yaml --output .tmp/final-black-box/library-qa-response.json
uv run python -m tagmemorag pilot run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --workdir .tmp/final-black-box/pilot --include-browser-qa --output .tmp/final-black-box/pilot/report.json
uv run python -m tagmemorag readiness browser-qa
git diff --check
```

## Review Questions

- `蒸汽很小怎么办？`
- `喷嘴怎么清洗？`
- `什么时候需要除垢？`
