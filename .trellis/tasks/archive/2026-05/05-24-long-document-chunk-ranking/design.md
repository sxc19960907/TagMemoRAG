# Design

## Boundary

Start with lexical ranking because the observed failures are within one source document and the relevant snippets contain exact ordinary query terms. Vector search and graph propagation should not be rewritten for this task.

## Candidate Approach

Extend lexical scoring so chunks with denser query-term coverage in the heading/body are preferred over chunks that only match broad page title or identity terms. The current scoring caps ordinary term hits and does not distinguish:

- scattered generic hits in a page title/heading
- specific body text that contains multiple query terms in the same evidence chunk

The likely shape is a small scoring refinement in `src/tagmemorag/lexical_search.py`, backed by unit tests. Search runtime and wave search should continue to consume `LexicalMatch.score` as before.

## Compatibility

- Preserve identity-field matching rules: source file/category/title should help model/code narrowing but should not count as ordinary topic evidence.
- Preserve CJK n-gram recovery for real manuals.
- Keep final scores bounded by the existing cap so lexical scoring does not swamp vector ranking globally.

## Validation Slices

- `tests/unit/test_lexical_search.py`
- `tests/unit/test_diag_mixed_domain_eval.py`
- `scripts/diag_mixed_domain_eval.py --stage-from-defaults`
- `scripts/diag_general_web_answer_eval.py` when seeded docs are present
- `scripts/diag_realmanuals_eval.py` or `tagmemorag eval run` against `realmanuals.jsonl`

