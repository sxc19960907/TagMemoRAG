const configEl = document.getElementById("qa-page-config");
const config = configEl ? JSON.parse(configEl.textContent || "{}") : {};

const state = {
  kbName: config.defaultKbName || "default",
  lastAnswerText: "",
  loadingTimer: null,
  loadingStageIndex: 0,
  turns: [],
  activeTurnId: "",
};

const suggestedQuestions = [
  "蒸汽很小怎么办？",
  "不出咖啡怎么办？",
  "什么时候需要除垢？",
  "喷嘴怎么清洗？",
];

const loadingStages = [
  "Understanding the question...",
  "Finding the most relevant manual passages...",
  "Composing a grounded answer...",
];

const el = {
  token: document.getElementById("qa-api-token"),
  questionForm: document.getElementById("qa-question-form"),
  question: document.getElementById("qa-question"),
  submit: document.getElementById("qa-submit"),
  status: document.getElementById("qa-status"),
  answerMeta: document.getElementById("qa-answer-meta"),
  answer: document.getElementById("qa-answer"),
  copyAnswer: document.getElementById("qa-copy-answer"),
  sourceMeta: document.getElementById("qa-source-meta"),
  sources: document.getElementById("qa-sources"),
  contextNote: document.getElementById("qa-context-note"),
  suggestions: document.getElementById("qa-suggestions"),
  followups: document.getElementById("qa-followups"),
  feedback: document.getElementById("qa-feedback"),
  feedbackNote: document.getElementById("qa-feedback-note"),
  history: document.getElementById("qa-history"),
  clearHistory: document.getElementById("qa-clear-history"),
};

function headers() {
  const out = { "Content-Type": "application/json" };
  const token = el.token ? el.token.value.trim() : "";
  if (token) out.Authorization = `Bearer ${token}`;
  return out;
}

function setStatus(message, kind = "") {
  el.status.textContent = message || "";
  el.status.className = kind ? `status-strip qa-status ${kind}` : "status-strip qa-status";
}

function setHidden(node, hidden) {
  if (node) node.hidden = hidden;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function updateLocationKb() {
  if (el.contextNote) {
    el.contextNote.textContent = "Ask a question and get an answer grounded in the available manuals.";
  }
}

async function requestAnswer(event) {
  event.preventDefault();
  const question = el.question.value.trim();
  if (!question) {
    setStatus("Enter a question first.", "error");
    el.question.focus();
    return;
  }

  await askQuestion(question, { useConversationContext: shouldUseConversationContext(question) });
}

async function askQuestion(question, options = {}) {
  updateLocationKb();
  const turn = addConversationTurn(question);
  renderPending();
  el.submit.disabled = true;
  setStatus("Asking...");

  try {
    const response = await fetch("/qa/answer", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        question,
        include_retrieve: true,
        conversation_context: options.useConversationContext ? conversationContextForRequest(turn.id) : [],
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.message || body.detail || `HTTP ${response.status}`);
    }
    updateConversationTurn(turn.id, {
      status: answerStatusFromBody(body),
      body,
    });
    if (state.activeTurnId === turn.id) {
      renderAnswer(body);
      setStatus("Answer ready.", "success");
    }
  } catch (error) {
    const message = userFacingError(error.message);
    updateConversationTurn(turn.id, {
      status: "error",
      errorMessage: message,
    });
    if (state.activeTurnId === turn.id) {
      renderError(error);
      setStatus(message, "error");
    }
  } finally {
    el.submit.disabled = false;
  }
}

function renderPending() {
  resetPostAnswerUi();
  state.lastAnswerText = "";
  el.answer.className = "qa-answer-message empty-state";
  el.answer.innerHTML = '<p class="qa-loading-stage">Understanding the question...</p>';
  el.answerMeta.textContent = "Preparing answer";
  if (el.copyAnswer) el.copyAnswer.disabled = true;
  el.sources.className = "qa-source-list empty-state";
  el.sources.textContent = "Finding sources...";
  el.sourceMeta.textContent = "Cited source snippets will appear here.";
  startLoadingStages();
}

function renderError(error) {
  stopLoadingStages();
  resetPostAnswerUi();
  state.lastAnswerText = "";
  el.answer.className = "qa-answer-message error";
  el.answer.textContent = userFacingError(error.message);
  el.answerMeta.textContent = "Request failed";
  if (el.copyAnswer) el.copyAnswer.disabled = true;
  el.sources.className = "qa-source-list empty-state";
  el.sources.textContent = "No sources available.";
  el.sourceMeta.textContent = "Sources unavailable.";
}

function renderAnswer(body) {
  stopLoadingStages();
  const answer = body.answer || {};
  const retrieve = body.retrieve || {};
  const kind = String(answer.kind || "unknown");

  if (kind === "answer") {
    state.lastAnswerText = String(answer.text || "");
    el.answer.className = "qa-answer-message";
    el.answer.innerHTML = renderAnswerText(answer.text || "");
    el.answerMeta.textContent = confidenceLabel(answer.confidence);
    if (el.copyAnswer) el.copyAnswer.disabled = !state.lastAnswerText;
    renderFollowups(answer.text || "", answer.citations || []);
    renderFeedback();
  } else {
    resetPostAnswerUi();
    state.lastAnswerText = "";
    el.answer.className = "qa-answer-message warn";
    const reason = answer.text || answer.refusal_reason || "I could not answer from the available manual content.";
    const hints = Array.isArray(answer.missing_evidence_hints) ? answer.missing_evidence_hints : [];
    el.answer.innerHTML = [
      `<p>${escapeHtml(userFacingReason(reason))}</p>`,
      ...hints.map((hint) => `<p class="muted">${escapeHtml(hint)}</p>`),
    ].join("");
    el.answerMeta.textContent = "No grounded answer available";
    if (el.copyAnswer) el.copyAnswer.disabled = true;
  }

  if (body.route && body.route.kind === "clarification") {
    renderClarificationCandidates(body.route.candidates || []);
  } else {
    renderSources(answer.citations || [], retrieve.evidence || []);
  }
}

function startLoadingStages() {
  stopLoadingStages();
  state.loadingStageIndex = 0;
  state.loadingTimer = window.setInterval(() => {
    state.loadingStageIndex = (state.loadingStageIndex + 1) % loadingStages.length;
    const stage = loadingStages[state.loadingStageIndex];
    const stageEl = el.answer.querySelector(".qa-loading-stage");
    if (stageEl) stageEl.textContent = stage;
    el.answerMeta.textContent = stage;
  }, 700);
}

function stopLoadingStages() {
  if (!state.loadingTimer) return;
  window.clearInterval(state.loadingTimer);
  state.loadingTimer = null;
}

function resetPostAnswerUi() {
  setHidden(el.followups, true);
  if (el.followups) el.followups.innerHTML = "";
  setHidden(el.feedback, true);
  if (el.feedbackNote) el.feedbackNote.textContent = "";
  if (el.feedback) {
    el.feedback.querySelectorAll("[data-feedback]").forEach((button) => {
      button.classList.remove("active");
      button.setAttribute("aria-pressed", "false");
    });
  }
}

function addConversationTurn(question) {
  const turn = {
    id: `turn-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    question,
    status: "pending",
    body: null,
    errorMessage: "",
    feedbackKind: "",
  };
  state.turns = [turn, ...state.turns].slice(0, 8);
  state.activeTurnId = turn.id;
  renderHistory();
  return turn;
}

function updateConversationTurn(turnId, patch) {
  state.turns = state.turns.map((turn) => (
    turn.id === turnId ? { ...turn, ...patch } : turn
  ));
  renderHistory();
}

function answerStatusFromBody(body) {
  const kind = String(body?.answer?.kind || "unknown");
  if (kind === "answer") return "answered";
  if (body?.route && body.route.kind === "clarification") return "clarification";
  return "refusal";
}

function conversationContextForRequest(activeTurnId) {
  return state.turns
    .filter((turn) => turn.id !== activeTurnId && turn.body && turn.status === "answered")
    .slice(0, 2)
    .reverse()
    .map((turn) => ({
      question: turn.question,
      answer: answerPreviewForContext(turn.body),
    }));
}

function answerPreviewForContext(body) {
  const answerText = String(body?.answer?.text || "").replace(/\s+/g, " ").trim();
  if (answerText) return answerText.slice(0, 700);
  const evidence = body?.retrieve?.evidence;
  if (Array.isArray(evidence) && evidence.length > 0) {
    return String(evidence[0].text || evidence[0].content || "").replace(/\s+/g, " ").trim().slice(0, 700);
  }
  return "";
}

function shouldUseConversationContext(question) {
  if (state.turns.length === 0) return false;
  const text = String(question || "").trim().toLowerCase();
  if (!text) return false;
  const followupMarkers = [
    "还是",
    "还不",
    "不行",
    "没用",
    "没有",
    "继续",
    "下一步",
    "然后",
    "这个",
    "那",
    "它",
    "still",
    "next",
    "then",
    "that",
    "it",
  ];
  return text.length <= 40 && followupMarkers.some((marker) => text.includes(marker));
}

function renderHistory() {
  if (!el.history) return;
  if (state.turns.length === 0) {
    el.history.className = "qa-history-list empty-state";
    el.history.textContent = "No questions yet.";
    if (el.clearHistory) el.clearHistory.disabled = true;
    return;
  }
  el.history.className = "qa-history-list";
  el.history.innerHTML = state.turns.map((turn) => `
    <button class="qa-history-item ${turn.id === state.activeTurnId ? "active" : ""}" type="button" data-turn-id="${escapeHtml(turn.id)}">
      <span>${escapeHtml(turn.question)}</span>
      <small>${escapeHtml(historyStatusLabel(turn.status))}</small>
    </button>
  `).join("");
  if (el.clearHistory) el.clearHistory.disabled = false;
  el.history.querySelectorAll("[data-turn-id]").forEach((button) => {
    button.addEventListener("click", () => restoreConversationTurn(button.dataset.turnId || ""));
  });
}

function historyStatusLabel(status) {
  if (status === "pending") return "Asking...";
  if (status === "answered") return "Answered";
  if (status === "clarification") return "Needs detail";
  if (status === "error") return "Failed";
  return "No answer";
}

function restoreConversationTurn(turnId) {
  const turn = state.turns.find((item) => item.id === turnId);
  if (!turn) return;
  state.activeTurnId = turn.id;
  if (el.question) el.question.value = turn.question;
  renderHistory();
  stopLoadingStages();
  if (turn.status === "pending") {
    renderPending();
    return;
  }
  if (turn.status === "error") {
    renderError({ message: turn.errorMessage || "Answer request failed." });
    return;
  }
  if (turn.body) {
    renderAnswer(turn.body);
  }
}

function clearHistory() {
  state.turns = [];
  state.activeTurnId = "";
  renderHistory();
}

function renderSuggestions() {
  if (!el.suggestions) return;
  el.suggestions.innerHTML = suggestedQuestions
    .map((question) => `<button class="qa-suggestion" type="button" data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`)
    .join("");
  el.suggestions.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      const question = button.dataset.question || "";
      el.question.value = question;
      askQuestion(question, { useConversationContext: false });
    });
  });
}

function renderFollowups(answerText, citations) {
  if (!el.followups) return;
  const questions = buildFollowupQuestions(answerText, citations).slice(0, 3);
  if (questions.length === 0) {
    setHidden(el.followups, true);
    return;
  }
  el.followups.innerHTML = `
    <span class="eyebrow">Follow up</span>
    <div class="qa-followup-list">
      ${questions.map((question) => `<button class="qa-followup-chip" type="button" data-followup="${escapeHtml(question)}">${escapeHtml(question)}</button>`).join("")}
    </div>
  `;
  setHidden(el.followups, false);
  el.followups.querySelectorAll("[data-followup]").forEach((button) => {
    button.addEventListener("click", () => {
      const question = button.dataset.followup || "";
      el.question.value = question;
      askQuestion(question, { useConversationContext: true });
    });
  });
}

function buildFollowupQuestions(answerText, citations) {
  const text = String(answerText || "").toLowerCase();
  const citationText = JSON.stringify(citations || []).toLowerCase();
  const combined = `${text} ${citationText}`;
  const questions = [];
  if (combined.includes("steam") || combined.includes("蒸汽")) {
    questions.push("蒸汽还是很小怎么办？", "喷嘴堵塞怎么判断？");
  }
  if (combined.includes("descal") || combined.includes("scale") || combined.includes("除垢")) {
    questions.push("除垢多久做一次？");
  }
  if (combined.includes("nozzle") || combined.includes("喷嘴")) {
    questions.push("喷嘴怎么彻底清洗？");
  }
  if (combined.includes("coffee") || combined.includes("咖啡")) {
    questions.push("还是不出咖啡怎么办？");
  }
  questions.push("如果还没恢复，下一步检查什么？", "哪些情况需要联系维修？");
  return [...new Set(questions)];
}

function renderFeedback() {
  if (!el.feedback) return;
  setHidden(el.feedback, false);
  const feedbackKind = activeConversationTurn()?.feedbackKind || "";
  el.feedback.querySelectorAll("[data-feedback]").forEach((button) => {
    const selected = button.dataset.feedback === feedbackKind;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  if (el.feedbackNote) {
    el.feedbackNote.textContent = feedbackNoteForKind(feedbackKind);
  }
}

function handleFeedback(kind) {
  if (!el.feedback) return;
  const turn = activeConversationTurn();
  if (turn) updateConversationTurn(turn.id, { feedbackKind: kind });
  el.feedback.querySelectorAll("[data-feedback]").forEach((button) => {
    const selected = button.dataset.feedback === kind;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  if (el.feedbackNote) {
    el.feedbackNote.textContent = feedbackNoteForKind(kind);
  }
}

function activeConversationTurn() {
  return state.turns.find((turn) => turn.id === state.activeTurnId);
}

function feedbackNoteForKind(kind) {
  if (kind === "helpful") return "Marked helpful for this answer.";
  if (kind === "not-helpful") return "Marked for review in this page session.";
  return "";
}

async function copyAnswer() {
  if (!state.lastAnswerText) return;
  try {
    await navigator.clipboard.writeText(state.lastAnswerText);
    setStatus("Answer copied.", "success");
  } catch (_error) {
    setStatus("Copy failed. Select the answer text to copy it manually.", "error");
  }
}

function confidenceLabel(confidence) {
  if (typeof confidence !== "number") return "Answer generated from manual evidence";
  if (confidence >= 0.75) return "High confidence";
  if (confidence >= 0.45) return "Medium confidence";
  return "Low confidence";
}

function renderAnswerText(text) {
  const lines = String(text || "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const firstStepIndex = lines.findIndex((line) => /^\d+\.\s+/.test(line));
  if (firstStepIndex >= 0) {
    const intro = lines.slice(0, firstStepIndex).map((line) => `<p>${renderInlineAnswerText(line)}</p>`).join("");
    const steps = lines.slice(firstStepIndex).map(renderAnswerStep).join("");
    return `${intro}<ol class="qa-answer-steps">${steps}</ol>`;
  }
  return `<p>${renderInlineAnswerText(text || "")}</p>`;
}

function renderAnswerStep(line) {
  const cleaned = line.replace(/^\d+\.\s+/, "");
  return `<li>${renderInlineAnswerText(cleaned)}</li>`;
}

function renderInlineAnswerText(text) {
  const parts = splitCitationMarkers(text || "");
  return parts
    .map((part) => {
      if (part.kind === "citation") return renderCitationChip(part.value);
      return escapeHtml(part.value);
    })
    .join("");
}

function splitCitationMarkers(text) {
  const pattern = /\[(cit_\d{3,})\]/g;
  const parts = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) {
      parts.push({ kind: "text", value: text.slice(cursor, match.index) });
    }
    parts.push({ kind: "citation", value: match[1] });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    parts.push({ kind: "text", value: text.slice(cursor) });
  }
  return parts;
}

function renderCitationChip(citationId) {
  const safeCitation = escapeHtml(citationId);
  return `<button class="qa-citation-chip" type="button" data-citation-target="${safeCitation}" aria-label="Show source ${safeCitation}">${safeCitation}</button>`;
}

function userFacingReason(reason) {
  const normalized = String(reason || "").replaceAll("_", " ");
  if (normalized === "generation disabled") return "Answer generation is not enabled for this server.";
  if (normalized === "generation failed") return "The answer service could not generate a response.";
  if (normalized === "insufficient evidence") return "I could not find enough manual evidence to answer that.";
  if (normalized === "needs clarification") return "I need one more detail before I can choose the right manual.";
  return normalized;
}

function userFacingError(message) {
  const text = String(message || "");
  if (text.includes("Knowledge base is not loaded")) {
    return "This knowledge base is not ready yet. Please import manuals and rebuild it before asking questions.";
  }
  if (text.includes("401") || text.toLowerCase().includes("unauthorized")) {
    return "A valid API token is required for this deployment.";
  }
  return text || "Answer request failed.";
}

function renderSources(citations, evidence) {
  const allowed = new Set(
    (Array.isArray(citations) ? citations : [])
      .map((citation) => citation.citation_id || citation)
      .filter(Boolean),
  );
  const items = (Array.isArray(evidence) ? evidence : []).filter((item) => {
    if (allowed.size === 0) return true;
    return allowed.has(item.citation_id || item.evidence_id || "");
  });

  if (items.length === 0) {
    el.sources.className = "qa-source-list empty-state";
    el.sources.textContent = "No cited sources returned.";
    el.sourceMeta.textContent = "No sources available.";
    return;
  }

  el.sources.className = "qa-source-list";
  el.sourceMeta.textContent = `${items.length} source${items.length === 1 ? "" : "s"} cited`;
  el.sources.innerHTML = items.map(renderSourceItem).join("");
  bindSourceToggles();
  bindCitationLinks();
}

function renderClarificationCandidates(candidates) {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    el.sources.className = "qa-source-list empty-state";
    el.sources.textContent = "No candidate manuals available.";
    el.sourceMeta.textContent = "More detail needed.";
    return;
  }
  el.sources.className = "qa-source-list";
  el.sourceMeta.textContent = "Possible manual contexts";
  el.sources.innerHTML = candidates
    .map((candidate) => `
      <article class="qa-source-item">
        <div class="evidence-head">
          <span>${escapeHtml(candidate.label || candidate.kb_name || "Manual")}</span>
        </div>
        <p class="muted">Add the product name, model, or error code to route this question.</p>
      </article>
    `)
    .join("");
}

function renderSourceItem(item) {
  const citation = item.citation_id || item.evidence_id || "source";
  const safeCitation = escapeHtml(citation);
  const source = item.source || item.source_file || "";
  const section = Array.isArray(item.section_path) ? item.section_path.join(" / ") : "";
  const text = item.text || item.content || "";
  const summary = summarizeSourceText(text);
  const canExpand = text.length > summary.length;
  return `
    <article id="qa-source-${safeCitation}" class="qa-source-item" data-citation-id="${safeCitation}">
      <div class="evidence-head">
        <span class="badge">${safeCitation}</span>
        <span class="muted">${escapeHtml(source)}</span>
      </div>
      ${section ? `<p class="qa-source-section">${escapeHtml(section)}</p>` : ""}
      <p class="qa-source-summary">${escapeHtml(summary)}</p>
      ${canExpand ? `<p class="qa-source-full" hidden>${escapeHtml(text)}</p><button class="qa-source-toggle" type="button" data-source-toggle>Show more</button>` : ""}
    </article>
  `;
}

function summarizeSourceText(text) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= 180) return normalized;
  const sentenceEnd = normalized.search(/[。.!?]\s/);
  if (sentenceEnd >= 80 && sentenceEnd <= 180) {
    return `${normalized.slice(0, sentenceEnd + 1).trim()}...`;
  }
  return `${normalized.slice(0, 177).trim()}...`;
}

function bindSourceToggles() {
  el.sources.querySelectorAll("[data-source-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const source = button.closest(".qa-source-item");
      if (!source) return;
      const full = source.querySelector(".qa-source-full");
      const summary = source.querySelector(".qa-source-summary");
      if (!full || !summary) return;
      const expanding = full.hidden;
      full.hidden = !expanding;
      summary.hidden = expanding;
      button.textContent = expanding ? "Show less" : "Show more";
    });
  });
}

function bindCitationLinks() {
  el.answer.querySelectorAll("[data-citation-target]").forEach((button) => {
    button.addEventListener("click", () => focusSource(button.dataset.citationTarget || ""));
  });
}

function focusSource(citationId) {
  const safeSelector = cssEscape(citationId);
  const source = el.sources.querySelector(`[data-citation-id="${safeSelector}"]`);
  if (!source) return;
  el.sources.querySelectorAll(".qa-source-item.active").forEach((item) => item.classList.remove("active"));
  source.classList.add("active");
  source.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(value);
  }
  return String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"');
}

el.questionForm.addEventListener("submit", requestAnswer);
if (el.copyAnswer) el.copyAnswer.addEventListener("click", copyAnswer);
if (el.feedback) {
  el.feedback.querySelectorAll("[data-feedback]").forEach((button) => {
    button.addEventListener("click", () => handleFeedback(button.dataset.feedback || ""));
  });
}
if (el.clearHistory) el.clearHistory.addEventListener("click", clearHistory);
renderSuggestions();
renderHistory();
updateLocationKb();
