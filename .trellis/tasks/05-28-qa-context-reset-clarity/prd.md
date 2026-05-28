# QA context reset clarity

## Goal

Make the user-facing `/qa` page clearly show when a short question will continue from prior conversation context and make the reset path obvious enough for non-technical users.

A user should be able to ask a follow-up such as `下一步呢？`, see that it is using prior context, then ask the same short phrase as a new standalone question without hidden conversation context affecting the answer.

## Confirmed Facts

- `/qa/answer` already accepts a bounded `conversation_context` array, and an empty array means the request is standalone.
- `qa_page.js` already auto-attaches recent answered turns for short follow-up-like questions via `shouldUseConversationContext(...)`.
- `qa_page.js` already has `requestNewQuestion()` and a `#qa-submit-new` button labeled `Ask as new`, but the page does not make the current context mode very visible before submit.
- The rendered answer can show `#qa-context-notice` after context is applied.
- Existing browser coverage verifies a contextual follow-up path, but it does not verify the reset path from the browser perspective.
- Backend architecture requires the user page to provide a way to ask a short follow-up as a new question by sending an empty `conversation_context`.

## Requirements

- Add a clear composer-level context mode indicator on `/qa` that updates as the question changes:
  - No prior answered turns or standalone question: show that the next ask will be treated as a new question.
  - Short follow-up-like question with prior answered turns: show that the next ask will continue from earlier context.
- Make the reset action obvious when context would be used. The action should keep using the existing `/qa/answer` API and send `conversation_context: []`.
- Preserve the existing automatic follow-up behavior for normal `Ask` submissions.
- Preserve session history, suggested follow-ups, source cards, feedback, and KB selection behavior.
- Keep the page browser-first and understandable. Do not expose debug identifiers, raw retrieve internals, plan ids, node ids, storage keys, blob keys, local paths, or full hidden context payloads.
- Add Chinese translations for new visible text.
- Add unit/static and browser coverage for the context reset path.

## Acceptance Criteria

- [x] `/qa` renders a context mode indicator near the composer.
- [x] The indicator changes to a continuation message for short follow-up-like questions after at least one answered turn exists.
- [x] Clicking `Ask as new` for a follow-up-like question sends an empty `conversation_context` and does not render `#qa-context-notice` for that answer.
- [x] Normal `Ask` still sends prior context for follow-up-like questions and renders `#qa-context-notice`.
- [x] Browser tests cover both contextual follow-up and reset-as-new behavior in one realistic flow.
- [x] Static tests cover the new shell element, JS renderer, styles, and i18n strings.
- [x] Existing unit/e2e non-performance tests remain green.

## Out of Scope

- Backend conversation persistence.
- Durable user memory or account-level chat history.
- LLM-based follow-up intent detection.
- Changing `/qa/answer` schema.
- Push to GitHub.
