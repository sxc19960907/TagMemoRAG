# Trial Operator Handoff - 2026-05-27

This is the current starting point for a small local TagMemoRAG trial after the browser-first RAG user experience completion program. It supersedes older post-merge handoff notes for day-to-day trial operation, while preserving those notes as historical context.

## Current Status

- `master` has been pushed to GitHub through `7630ba7`.
- The browser-first Q&A flow passed black-box acceptance.
- The local deterministic demo does not require API keys, Qdrant, S3, or external model services.
- The retained pilot command can include browser QA readiness in the same report.
- Report retention and GitHub CI handoff are summarized in `docs/trial-report-ci-handoff.md`.

## Start A Local Trial

From the repository root:

```bash
uv run python -m tagmemorag demo library-qa \
  --config examples/config/qa-demo.yaml \
  --output .tmp/tagmemorag-qa-demo/library-qa-response.json

uv run python -m tagmemorag serve \
  --host 127.0.0.1 \
  --port 8000 \
  --config examples/config/qa-demo.yaml
```

Open:

```text
http://127.0.0.1:8000/
```

The local demo config has auth disabled, so the API token field can stay empty.

## Browser Dashboard Map

Use `kb_name=default` for the local demo.

| Surface | URL | Use it for |
| --- | --- | --- |
| RAG Workbench | `/admin/rag-workbench?kb_name=default` | Inspect retrieval and answer payloads for one-off questions. |
| Manual Library | `/admin/manual-library?kb_name=default` | Upload manuals, check searchable state, trigger rebuilds, and follow next-step guidance. |
| Ask Q&A | `/qa?kb_name=default` | Normal user Q&A experience with answers, citations, source cards, language switch, and feedback. |
| Retrieval Quality | `/admin/retrieval-quality?kb_name=default` | Review helpful/not-helpful feedback, add expected evidence, preview/export eval drafts, and launch eval runs. |
| RAG Readiness | `/admin/rag-readiness?kb_name=default` | See KB readiness, recommendations, latest eval report links, and next actions. |
| Eval Report | `/admin/eval-report?kb_name=default` | Review retained eval reports and case-level failures. |
| People & Access | `/admin/people?kb_name=default` | Inspect config-backed API keys and browser token guidance. |

Use the **English / 中文** switcher to verify the browser UI language for trial participants.

## Trial Smoke Script

Before inviting a user to try the browser page, retain one pilot report:

```bash
uv run python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/trial-ops-pilot \
  --include-browser-qa \
  --output .tmp/trial-ops-pilot/report.json
```

Expected local profile result:

- overall status: `passed`
- `readiness_smoke: passed`
- `browser_qa_readiness: passed`
- `answer_quality: passed`
- `eval: passed`

If the browser flow was changed broadly, add `--browser-qa-full`.

For CI handoff and retained evidence details, see [Trial Report And CI Handoff](trial-report-ci-handoff.md).

## First User Questions

For the demo manual, ask:

- `蒸汽很小怎么办？`
- `喷嘴怎么清洗？`
- `什么时候需要除垢？`
- `不出咖啡怎么办？`

Expected behavior:

- the answer should cite `demo/demo-service-manual.md`;
- citation chips should focus matching source cards;
- the source cards should show section names and cited text;
- weak or off-topic questions should show recovery guidance rather than pretending to know.

## Feedback Triage Loop

When a user marks an answer **Not helpful**:

1. On the Q&A page, click **Review this case**.
2. Confirm Retrieval Quality opens with the matching feedback row selected.
3. Read selected evidence and answer context.
4. Use the **Triage next action** panel to choose one route:
   - dismiss the case if the answer was acceptable or the question was out of scope;
   - use selected evidence or add expected evidence, then preview/export an eval draft if it is a useful regression case;
   - mark the case triaged after the expected evidence or operator note captures the decision;
   - record an operator note if the manual content or metadata needs cleanup.
5. Run or retain the suggested eval report before treating the case as covered.

## Upload And Rebuild Recovery

For trial manuals:

- Use Manual Library upload for `.md`, `.txt`, or text-based `.pdf` files.
- Keep **Trigger rebuild** enabled for the simplest path.
- Watch the Next step panel after upload.
- If rebuild is needed, click **Rebuild now**.
- If rebuild fails, the previous searchable KB remains active when one exists; inspect **Recovery** and **Rebuild Queue**, fix the reported input/config issue, then use **Retry rebuild** or **Rebuild now**.

Do not use image-only scanned PDFs for the local demo trial unless OCR is explicitly enabled and verified.

## Auth And Live Provider Boundaries

- Local demo profile: auth disabled, hashing embeddings, local NPZ vectors, noop answer provider.
- Auth-enabled deployments: paste a Bearer token into the browser token field; the UI stores it in `sessionStorage` for the current browser session.
- Live provider, Qdrant, S3, and production-profile checks are opt-in. Use the production-provider and deployment runbooks before a live-provider trial.

## Deeper References

- [Browser RAG Quick Start](browser-rag-quick-start.md)
- [Production Pilot Runbook](production-pilot-runbook.md)
- [Trial Report And CI Handoff](trial-report-ci-handoff.md)
- [RAG Quality Gates](rag-quality-gates.md)
- [Production Provider Smoke Runbook](production-provider-smoke-runbook.md)
- [Production Deployment Operations](production-deployment-operations.md)
