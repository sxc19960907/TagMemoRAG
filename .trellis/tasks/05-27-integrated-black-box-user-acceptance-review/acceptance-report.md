# Integrated Black Box User Acceptance Report

## Summary

Status: passed.

The browser-first RAG flow is usable for the deterministic local demo profile. A normal user can open the Q&A page, see the active `default` knowledge base, ask suggested manual questions, inspect cited sources, switch the UI language, submit not-helpful feedback, and jump directly into Retrieval Quality with the feedback row selected.

## Browser Review Evidence

- Demo seed command passed and wrote `.tmp/final-black-box/library-qa-response.json`.
- Local browser review server: `http://127.0.0.1:63691/qa?kb_name=default`.
- Screenshot retained at `.tmp/final-black-box/qa-acceptance.png`.
- QA first screen showed:
  - active KB: `default`
  - KB selector: `default - ready - 12 chunks`
  - suggested questions for weak steam, no coffee, descaling, and nozzle cleaning
  - empty answer/source guidance

## Question Review

| Question | Result |
| --- | --- |
| `蒸汽很小怎么办？` | Useful answer citing `蒸汽很小` and related coffee troubleshooting evidence. |
| `喷嘴怎么清洗？` | Useful answer citing `喷嘴清洗` and weak-steam evidence. |
| `什么时候需要除垢？` | Useful answer citing `除垢` and weak-steam evidence. |

Citation chips focused source cards successfully. Source cards displayed `demo/demo-service-manual.md`, citation IDs, section names, and cited manual passages.

## Language And Feedback

- Language switch from English to Chinese showed `手册问答`, then switching back restored `Manual Q&A`.
- Not-helpful feedback saved from the QA page.
- The QA page displayed `Review this case` with `/admin/retrieval-quality?kb_name=default&feedback_id=77437e7fddf5c8c0`.
- Retrieval Quality opened from that link and auto-selected feedback `77437e7fddf5c8c0`.
- Retrieval Quality detail showed the query, Q&A source, not-helpful outcome, trace/search/retrieve/plan IDs, and selected evidence summary.

## Automation Notes

The in-app browser automation layer could not type into the textarea because its virtual clipboard integration was unavailable. This was treated as an automation limitation, not a product defect, because:

- the textarea was visible and focused in the browser;
- suggested-question clicks exercised the same user-facing answer path;
- the automated browser readiness gate separately filled the textbox and passed.

## Final Gates

```text
uv run python -m tagmemorag pilot run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --workdir .tmp/final-black-box/pilot --include-browser-qa --output .tmp/final-black-box/pilot/report.json
```

Result: passed.

Pilot stages:

- `config_validate:passed`
- `provider_probe:skipped`
- `readiness_smoke:passed`
- `browser_qa_readiness:passed`
- `answer_quality:passed`
- `eval:passed`

```text
uv run python -m tagmemorag readiness browser-qa
```

Result: passed.

```text
git diff --check
```

Result: passed.

## Blocking Defects

None found.
