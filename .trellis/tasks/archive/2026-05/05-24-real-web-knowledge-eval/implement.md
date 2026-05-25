# Implementation Plan

1. [x] Add grouped real-web source URLs to `scripts/seed_general_web_eval.sh` without committing fetched content.
2. [x] Extend `tests/fixtures/eval/general_web.jsonl` with MDN, USAGov, and IRS retrieval cases.
3. [x] Add or update unit tests that inspect the seed script/source expectations without network access.
4. [x] Run the expanded seed script and retrieval eval; adjust case wording only if importer output proves different.
5. [x] Run live answer diagnostic over the expanded seeded corpus.
6. [x] Run mixed-domain diagnostic with the expanded public-web corpus and real manuals.
7. [x] Update README and backend architecture notes.
8. [ ] Run focused tests, `git diff --check`, archive task, commit code/docs, and record journal.

## Validation Commands

```bash
.venv/bin/python -m pytest tests/unit/test_public_web_import.py tests/unit/test_diag_general_web_answer_eval.py tests/unit/test_diag_mixed_domain_eval.py -q
scripts/seed_general_web_eval.sh
.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/general_web.jsonl --docs .tmp/general-web-eval/general_web --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/real-web-knowledge-eval.json
.venv/bin/python scripts/diag_general_web_answer_eval.py --docs .tmp/general-web-eval/general_web --suite tests/fixtures/eval/general_web.jsonl --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 8 --output .tmp/eval/real-web-knowledge-answer.json
.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/real-web-knowledge-mixed.json
git diff --check
```

## Risk Points

- Public pages can change wording. Use stable official docs and avoid over-specific long snippets.
- Current HTML parser extracts broad visible text, including some navigation. Cases should target body prose that survives extraction.
- Google Help pages can vary by locale or UI; use a stable English URL and broad support-article query terms.
