# Browser RAG Quick Start

This guide is the shortest local path for trying TagMemoRAG as a browser user. It uses hashing embeddings, local NPZ vectors, the managed manual library, and the noop answer provider, so it does not need API keys, Qdrant, S3, or external model services.

For a trial operator view with dashboard links, retained pilot reports, and feedback triage, start with [Trial Operator Handoff - 2026-05-27](trial-operator-handoff-2026-05-27.md).

## 1. Install

From the repository root:

```bash
uv sync --extra dev
```

If you do not use `uv`, install the package with development extras:

```bash
pip install -e ".[dev]"
```

The commands below use `uv run python`. If you installed with `pip` into a local virtualenv, use `.venv/bin/python` instead.

## 2. Seed The Demo KB

Create the local demo manual, rebuild the managed library, and verify that a cited answer can be produced:

```bash
uv run python -m tagmemorag demo library-qa \
  --config examples/config/qa-demo.yaml \
  --clean \
  --output .tmp/tagmemorag-qa-demo/library-qa-response.json
```

A successful run prints `"status": "passed"`. The demo writes local data under `.tmp/tagmemorag-qa-demo/`.
The `--clean` flag resets that demo workspace first, which is recommended for first-run checks and black-box verification.

## 3. Start The Server

```bash
uv run python -m tagmemorag serve \
  --host 127.0.0.1 \
  --port 8000 \
  --config examples/config/qa-demo.yaml
```

Leave this command running while you use the browser.

## 4. Open The Browser UI

Open:

```text
http://127.0.0.1:8000/
```

The root page opens RAG Workbench for `kb_name=default`. From there you can use the top navigation to move between:

- RAG Workbench: `http://127.0.0.1:8000/admin/rag-workbench?kb_name=default`
- Manual Library: `http://127.0.0.1:8000/admin/manual-library?kb_name=default`
- Ask Q&A: `http://127.0.0.1:8000/qa?kb_name=default`

The demo config has auth disabled, so the API token field can stay empty.

Use the **English / 中文** selector to switch the browser UI language. The selection is remembered across the RAG Workbench, Manual Library, Retrieval Quality, People & Access, and Q&A pages.

## 5. Confirm The Seeded Manual

In Manual Library, confirm that `demo-service-manual` is visible, searchable, and clear of pending rebuild state. Then click **Ask Q&A**.

Ask:

```text
蒸汽很小怎么办？
```

The answer should mention cleaning the nozzle, checking the water tank, or descaling, and the source list should include `demo-service-manual.md`.

The answer appears in a conversation layout. Click a `cit_###` citation chip in the answer to focus the matching source card. Source cards show the cited manual passage and section context when available.

## 6. Try Your Own Manual

There are two supported browser-first ways to add your own manual.

### Option A: Start From Ask Q&A

Use this path when the KB is empty or when you want the shortest normal-user flow:

1. Open `http://127.0.0.1:8000/qa?kb_name=default`.
2. In the answer area, confirm the page says **Start by adding a manual**.
3. Use the left-side **Add manual** form to choose a `.md`, `.txt`, text-based `.pdf`, or readable `.docx` manual.
4. Fill or confirm the title, source file, category, language, and tags.
5. Click **Upload and index**.
6. Wait for **Manual is indexed. Ask a question about it below.**
7. Click one of the suggested questions generated from the uploaded manual, or type your own question.
8. Confirm the answer cites the uploaded manual in the Sources panel.

If indexing fails, use the recovery links shown on the Q&A page: **Check readiness** opens RAG Readiness, and **Open Manual Library** opens the managed library for the active KB.

### Option B: Start From Manual Library

Use this path when you want the operator view of metadata, searchable state, and rebuild status:

1. Click **Upload**.
2. Choose a `.md`, `.txt`, text-based `.pdf`, or readable `.docx` manual.
3. Fill required metadata: `Manual ID`, `Title`, `Source file`, and `Category`.
4. Keep **Trigger rebuild** checked.
5. Submit the upload.
6. Watch the **Next step** panel.
7. If it says **Manual uploaded, rebuild needed**, click **Rebuild now**.
8. When it says **Manual is ready for Q&A**, click **Ask in Q&A**.
9. Ask a question that the manual can answer.

If the page says the KB is not ready, return to Manual Library and run **Rebuild**. If an answer says the evidence is insufficient, try a question that more directly matches the uploaded manual text.

## Optional Browser Smoke

To run the same path as an automated browser check:

```bash
TAGMEMORAG_RUN_BROWSER_UI=1 \
  .venv/bin/python -m pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_manual_rebuild_then_qa_user_flow -q -s
```

The full opt-in browser suite is:

```bash
TAGMEMORAG_RUN_BROWSER_UI=1 \
  .venv/bin/python -m pytest tests/integration/test_browser_admin_ui.py -q
```
