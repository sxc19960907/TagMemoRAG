# Implementation Plan

## Checklist

- [x] Confirm planning artifacts and activate the task.
- [x] Build a structured general-web retrieval diagnostic from existing reports.
- [x] Write `diagnostic-notes.md` with per-case evidence and an explicit safety
      decision.
- [x] If a safe signal exists, implement the narrowest deterministic scoring
      change and add focused unit coverage.
- [ ] Rerun general-web retrieval and compare MRR, recall, and hit@k.
- [ ] Rerun release-readiness stages that could regress from ranking changes.
- [ ] Update specs only if a durable scoring contract or diagnostic convention is
      learned.
- [ ] Commit only this task's artifacts and any intentional code/test/spec
      changes.

## Validation Commands

Use the existing local hashing config and seeded docs:

```text
scripts/seed_general_web_eval.sh
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/general_web.jsonl \
  --docs .tmp/general-web-eval/general_web \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web \
  --top-k 8
```

If ranking code changes, also run the relevant regression matrix:

```text
.venv/bin/pytest \
  tests/unit/test_retrieval.py \
  tests/unit/test_answer_generator.py \
  tests/unit/test_lexical_search.py \
  tests/unit/test_release_readiness.py \
  tests/unit/test_search_runtime_phase1.py \
  -q
```

Then regenerate or inspect release-readiness reports covering:

- general-web retrieval/context/answer
- multi-format retrieval/context/answer
- mixed-domain retrieval
- realmanuals retrieval
- product QA answer quality

## Risk Points

- `src/tagmemorag/lexical_search.py` is shared by product manuals and public web;
  broad changes can regress realmanual retrieval.
- `src/tagmemorag/wave_searcher.py` sorts with `lexical_evidence_score`; avoid
  WAVE/geodesic changes in this task.
- Eval reports under `.tmp/` are runtime outputs and should not be committed.
- `.codegraph/` and `.mcp.json` are unrelated untracked files and must remain
  untouched.
