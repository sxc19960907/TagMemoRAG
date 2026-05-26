# Implementation Plan: RAG quality workflow integration

1. Read task artifacts and applicable specs.
2. Start task with `task.py start`.
3. Add Workbench Eval Report link:
   - template link.
   - JS link update with KB propagation.
   - unit assertions.
4. Add `question` prefill:
   - Q&A page reads URL query and fills textarea.
   - Workbench reads URL query and fills textarea.
   - status copy is nonintrusive.
5. Add Eval Report case actions:
   - Build case-specific Q&A and Workbench hrefs.
   - Render compact buttons inside each case card.
6. Add/adjust i18n and CSS if needed.
7. Validate:
   - `node --check src/tagmemorag/web/static/qa_page.js`
   - `node --check src/tagmemorag/web/static/rag_workbench.js`
   - `node --check src/tagmemorag/web/static/eval_report.js`
   - `node --check src/tagmemorag/web/static/i18n.js`
   - `uv run pytest tests/unit/test_manual_library_ui.py -q`
   - browser smoke for eval report case action.
   - `git diff --check`
8. Commit implementation, task record, archive/journal, push.
