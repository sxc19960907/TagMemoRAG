import { authHeadersFromToken, bindSharedApiToken } from "./admin_token.js";
import { initI18n, t, translatePage } from "./i18n.js";

const configEl = document.getElementById("qa-page-config");
const config = configEl ? JSON.parse(configEl.textContent || "{}") : {};

const state = {
  kbName: config.defaultKbName || "default",
  lastAnswerText: "",
  loadingTimer: null,
  loadingStageIndex: 0,
  turns: [],
  activeTurnId: "",
  kbReady: false,
  uploadedManual: null,
  dynamicSuggestions: [],
};

const sessionMemoryKey = `tagmemorag:qa:session:${state.kbName}`;
const sessionMemoryVersion = 1;

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
  submitNew: document.getElementById("qa-submit-new"),
  status: document.getElementById("qa-status"),
  answerMeta: document.getElementById("qa-answer-meta"),
  answer: document.getElementById("qa-answer"),
  copyAnswer: document.getElementById("qa-copy-answer"),
  sourceMeta: document.getElementById("qa-source-meta"),
  sources: document.getElementById("qa-sources"),
  contextNote: document.getElementById("qa-context-note"),
  readinessLink: document.getElementById("qa-readiness-link"),
  activeKb: document.getElementById("qa-active-kb"),
  kbSelect: document.getElementById("qa-kb-select"),
  kbNote: document.getElementById("qa-kb-note"),
  manualLibraryLink: document.getElementById("qa-manual-library-link"),
  uploadForm: document.getElementById("qa-upload-form"),
  uploadFile: document.getElementById("qa-upload-file"),
  uploadTitle: document.getElementById("qa-upload-title"),
  uploadCategory: document.getElementById("qa-upload-category"),
  uploadSource: document.getElementById("qa-upload-source"),
  uploadLanguage: document.getElementById("qa-upload-language"),
  uploadTags: document.getElementById("qa-upload-tags"),
  uploadMessages: document.getElementById("qa-upload-messages"),
  uploadSubmit: document.getElementById("qa-upload-submit"),
  suggestions: document.getElementById("qa-suggestions"),
  followups: document.getElementById("qa-followups"),
  feedback: document.getElementById("qa-feedback"),
  feedbackNote: document.getElementById("qa-feedback-note"),
  history: document.getElementById("qa-history"),
  clearHistory: document.getElementById("qa-clear-history"),
};

function headers() {
  const out = { "Content-Type": "application/json" };
  return { ...out, ...authHeadersFromToken(el.token ? el.token.value : "") };
}

function setStatus(message, kind = "") {
  el.status.textContent = message ? t(message) : "";
  el.status.className = kind ? `status-strip qa-status ${kind}` : "status-strip qa-status";
}

function updateLinks() {
  if (el.readinessLink) {
    el.readinessLink.href = `/admin/rag-readiness?kb_name=${encodeURIComponent(state.kbName || "default")}`;
  }
  if (el.manualLibraryLink) {
    el.manualLibraryLink.href = `/admin/manual-library?kb_name=${encodeURIComponent(state.kbName || "default")}`;
  }
  if (el.activeKb) {
    el.activeKb.textContent = state.kbName || "default";
  }
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
    el.contextNote.textContent = t("Ask a question and get an answer grounded in {kb}.", { kb: state.kbName || "default" });
    translatePage();
  }
}

function currentQuestionParam() {
  const params = new URLSearchParams(window.location.search);
  return params.get("question") || "";
}

function qaUrlForKb(kbName) {
  const params = new URLSearchParams();
  params.set("kb_name", kbName || "default");
  const question = currentQuestionParam();
  if (question) params.set("question", question);
  return `/qa?${params.toString()}`;
}

function kbOptionLabel(item) {
  const name = String(item?.kb_name || state.kbName || "default");
  const count = Number(item?.node_count || 0);
  const status = String(item?.status || "");
  const parts = [name];
  if (status) parts.push(status);
  if (Number.isFinite(count) && count > 0) parts.push(t("{count} chunks", { count }));
  return parts.join(" · ");
}

function renderKbOptions(kbs) {
  if (!el.kbSelect) return;
  const entries = Array.isArray(kbs) ? [...kbs] : [];
  const activeEntry = entries.find((item) => String(item?.kb_name || "") === state.kbName);
  state.kbReady = Boolean(activeEntry && Number(activeEntry.node_count || 0) > 0 && String(activeEntry.status || "") !== "rebuilding");
  if (!entries.some((item) => String(item?.kb_name || "") === state.kbName)) {
    entries.unshift({ kb_name: state.kbName || "default" });
  }
  el.kbSelect.innerHTML = entries
    .map((item) => {
      const name = String(item?.kb_name || state.kbName || "default");
      return `<option value="${escapeHtml(name)}">${escapeHtml(kbOptionLabel(item))}</option>`;
    })
    .join("");
  el.kbSelect.value = state.kbName || "default";
  el.kbSelect.disabled = entries.length <= 1;
  if (el.kbNote) {
    el.kbNote.textContent = entries.length > 1
      ? t("Switching knowledge bases starts a separate Q&A session.")
      : t("Only this knowledge base is available for your token.");
  }
}

async function loadKnowledgeBases() {
  if (!el.kbSelect) return;
  renderKbOptions([{ kb_name: state.kbName || "default" }]);
  try {
    const response = await fetch("/kb", { headers: authHeadersFromToken(el.token ? el.token.value : "") });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || body.detail || `HTTP ${response.status}`);
    renderKbOptions(body.kbs || []);
    renderFirstRunGuidance();
  } catch (_error) {
    if (el.kbNote) {
      el.kbNote.textContent = t("Knowledge base list unavailable. You can keep asking in {kb}.", { kb: state.kbName || "default" });
    }
    renderFirstRunGuidance();
  }
}

function handleKbSelection() {
  const selected = el.kbSelect ? el.kbSelect.value.trim() : "";
  if (!selected || selected === state.kbName) return;
  window.location.assign(qaUrlForKb(selected));
}

function applyQuestionPrefill() {
  const params = new URLSearchParams(window.location.search);
  const question = params.get("question") || "";
  if (!question) return;
  el.question.value = question;
  setStatus(t("Question prefilled. Review it, then ask when ready."), "success");
}

async function requestAnswer(event) {
  event.preventDefault();
  const question = el.question.value.trim();
  if (!question) {
    setStatus(t("Enter a question first."), "error");
    el.question.focus();
    return;
  }

  await askQuestion(question, { useConversationContext: shouldUseConversationContext(question) });
}

async function requestNewQuestion() {
  const question = el.question.value.trim();
  if (!question) {
    setStatus(t("Enter a question first."), "error");
    el.question.focus();
    return;
  }
  await askQuestion(question, { useConversationContext: false });
}

async function askQuestion(question, options = {}) {
  updateLocationKb();
  const turn = addConversationTurn(question);
  const contextTurns = options.useConversationContext ? conversationContextForRequest(turn.id) : [];
  updateConversationTurn(turn.id, {
    usedContext: contextTurns.length > 0,
    contextSummary: contextTurns.map((item) => ({ question: item.question })),
  });
  renderPending(question);
  el.submit.disabled = true;
  if (el.submitNew) el.submitNew.disabled = true;
  setStatus(t("Asking..."));

  try {
    const response = await fetch("/qa/answer", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        question,
        include_retrieve: true,
        conversation_context: contextTurns,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.message || body.detail || `HTTP ${response.status}`);
    }
    updateConversationTurn(turn.id, {
      status: answerStatusFromBody(body),
      body,
      usedContext: Boolean(body.context?.applied),
      contextSummary: Array.isArray(body.context?.summary) ? body.context.summary : contextTurns.map((item) => ({ question: item.question })),
    });
    if (state.activeTurnId === turn.id) {
      renderAnswer(body);
      setStatus(t("Answer ready."), "success");
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
    updateSubmitNewState();
  }
}

function renderPending(question = "") {
  resetPostAnswerUi();
  state.lastAnswerText = "";
  el.answer.className = "qa-answer-message";
  el.answer.innerHTML = renderConversationShell(question, renderLoadingState());
  el.answerMeta.textContent = t("Checking manuals");
  if (el.copyAnswer) el.copyAnswer.disabled = true;
  el.sources.className = "qa-source-list empty-state";
  el.sources.innerHTML = `
    <div class="qa-source-placeholder">
      <strong>${t("Finding cited passages")}</strong>
      <p>${t("Sources will appear here as soon as the answer is ready.")}</p>
    </div>
  `;
  el.sourceMeta.textContent = t("Retrieving manual evidence...");
  startLoadingStages();
}

function renderError(error) {
  stopLoadingStages();
  resetPostAnswerUi();
  state.lastAnswerText = "";
  el.answer.className = "qa-answer-message error";
  const question = activeConversationTurn()?.question || "";
  el.answer.innerHTML = renderConversationShell(question, renderRecoveryState(userFacingError(error.message)));
  el.answerMeta.textContent = t("Request failed");
  if (el.copyAnswer) el.copyAnswer.disabled = true;
  el.sources.className = "qa-source-list empty-state";
  el.sources.innerHTML = `
    <div class="qa-source-placeholder">
      <strong>${t("No sources available.")}</strong>
      <p>${t("Sources are shown after a successful grounded answer.")}</p>
    </div>
  `;
  el.sourceMeta.textContent = t("Sources unavailable.");
}

function renderAnswer(body) {
  stopLoadingStages();
  const answer = body.answer || {};
  const retrieve = body.retrieve || {};
  const kind = String(answer.kind || "unknown");

  if (kind === "answer") {
    state.lastAnswerText = String(answer.text || "");
    el.answer.className = "qa-answer-message";
    el.answer.innerHTML = renderConversationShell(body.question || activeConversationTurn()?.question || "", renderAnswerText(answer.text || ""));
    el.answerMeta.textContent = confidenceLabel(answer.confidence);
    if (el.copyAnswer) el.copyAnswer.disabled = !state.lastAnswerText;
    renderContextNotice(body.context);
    renderFollowups(answer.text || "", answer.citations || []);
    renderFeedback();
  } else {
    resetPostAnswerUi();
    state.lastAnswerText = "";
    el.answer.className = "qa-answer-message warn";
    const reason = answer.text || answer.refusal_reason || t("I could not answer from the available manual content.");
    const hints = Array.isArray(answer.missing_evidence_hints) ? answer.missing_evidence_hints : [];
    el.answer.innerHTML = renderConversationShell(body.question || activeConversationTurn()?.question || "", [
      `<p>${escapeHtml(userFacingReason(reason))}</p>`,
      ...hints.map((hint) => `<p class="muted">${escapeHtml(hint)}</p>`),
      renderRecoveryState(userFacingReason(reason)),
    ].join(""));
    el.answerMeta.textContent = t("No grounded answer available");
    if (el.copyAnswer) el.copyAnswer.disabled = true;
    renderContextNotice(body.context);
  }

  if (body.route && body.route.kind === "clarification") {
    renderClarificationCandidates(body.route.candidates || []);
  } else {
    renderSources(answer.citations || [], retrieve.evidence || []);
  }
}

function renderConversationShell(question, answerHtml) {
  const questionHtml = question
    ? `
      <section class="qa-message-row user">
        <div class="qa-message-bubble">
          <span class="eyebrow">${t("Your question")}</span>
          <p>${escapeHtml(question)}</p>
        </div>
      </section>
    `
    : "";
  return `
    <div class="qa-message-stack">
      ${questionHtml}
      <section class="qa-message-row assistant">
        <div class="qa-message-bubble">
          <span class="eyebrow">${t("Manual answer")}</span>
          ${answerHtml}
        </div>
      </section>
    </div>
  `;
}

function renderLoadingState() {
  return `
    <div class="qa-progress-card" aria-live="polite">
      <strong>${t("Working on your answer")}</strong>
      <p class="qa-loading-stage">${t("Understanding the question...")}</p>
      <ol>
        <li>${t("Match the question to the active knowledge base.")}</li>
        <li>${t("Retrieve the most relevant manual passages.")}</li>
        <li>${t("Draft an answer with citations you can inspect.")}</li>
      </ol>
    </div>
  `;
}

function renderRecoveryState(message) {
  return `
    <div class="qa-recovery-card">
      <strong>${t("Could not complete this answer")}</strong>
      <p>${escapeHtml(t(message))}</p>
      <ul>
        <li>${t("Try asking again with the product model, symptom, or error code.")}</li>
        <li>${t("Use Ask as new if the previous context is confusing the question.")}</li>
        <li>${t("Check RAG Readiness if this keeps failing.")}</li>
      </ul>
      <a class="button-link compact" href="/admin/rag-readiness?kb_name=${encodeURIComponent(state.kbName || "default")}">${t("Check readiness")}</a>
    </div>
  `;
}

function startLoadingStages() {
  stopLoadingStages();
  state.loadingStageIndex = 0;
  state.loadingTimer = window.setInterval(() => {
    state.loadingStageIndex = (state.loadingStageIndex + 1) % loadingStages.length;
    const stage = loadingStages[state.loadingStageIndex];
    const stageEl = el.answer.querySelector(".qa-loading-stage");
    if (stageEl) stageEl.textContent = t(stage);
    el.answerMeta.textContent = t(stage);
  }, 700);
}

function stopLoadingStages() {
  if (!state.loadingTimer) return;
  window.clearInterval(state.loadingTimer);
  state.loadingTimer = null;
}

function resetPostAnswerUi() {
  renderContextNotice(null);
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
    feedbackId: "",
    feedbackStatus: "",
    feedbackPending: false,
    usedContext: false,
    contextSummary: [],
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
  saveSessionMemory();
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
    el.history.textContent = t("No questions yet.");
    if (el.clearHistory) el.clearHistory.disabled = true;
    return;
  }
  el.history.className = "qa-history-list";
  el.history.innerHTML = state.turns.map((turn) => `
    <button class="qa-history-item ${turn.id === state.activeTurnId ? "active" : ""}" type="button" data-turn-id="${escapeHtml(turn.id)}">
      <span>${escapeHtml(turn.question)}</span>
      <small class="qa-history-status">
        <span>${escapeHtml(historyStatusLabel(turn.status))}</span>
        ${turn.usedContext ? '<span class="qa-context-pill">Context</span>' : ""}
      </small>
    </button>
  `).join("");
  if (el.clearHistory) el.clearHistory.disabled = false;
  el.history.querySelectorAll("[data-turn-id]").forEach((button) => {
    button.addEventListener("click", () => restoreConversationTurn(button.dataset.turnId || ""));
  });
}

function loadSessionMemory() {
  let saved;
  try {
    saved = JSON.parse(window.sessionStorage.getItem(sessionMemoryKey) || "{}");
  } catch (_error) {
    clearSessionMemory();
    return;
  }
  if (!saved || saved.version !== sessionMemoryVersion || !Array.isArray(saved.turns)) return;
  state.turns = saved.turns
    .map(normalizeSavedTurn)
    .filter(Boolean)
    .slice(0, 8);
  state.activeTurnId = state.turns.some((turn) => turn.id === saved.activeTurnId)
    ? saved.activeTurnId
    : (state.turns[0]?.id || "");
}

function normalizeSavedTurn(rawTurn) {
  if (!rawTurn || typeof rawTurn !== "object") return null;
  const question = String(rawTurn.question || "").trim().slice(0, 1000);
  if (!question) return null;
  const status = rawTurn.status === "answered" || rawTurn.status === "clarification" || rawTurn.status === "refusal"
    ? rawTurn.status
    : "error";
  return {
    id: String(rawTurn.id || `saved-${Date.now()}-${Math.random().toString(16).slice(2)}`),
    question,
    status,
    body: rawTurn.body ? sanitizeAnswerBody(rawTurn.body) : null,
    errorMessage: status === "error" ? String(rawTurn.errorMessage || "This answer was interrupted before reload.").slice(0, 300) : "",
    feedbackKind: rawTurn.feedbackKind === "helpful" || rawTurn.feedbackKind === "not-helpful" ? rawTurn.feedbackKind : "",
    feedbackId: String(rawTurn.feedbackId || "").slice(0, 120),
    feedbackStatus: rawTurn.feedbackStatus === "saved" || rawTurn.feedbackStatus === "failed" ? rawTurn.feedbackStatus : "",
    feedbackPending: false,
    usedContext: Boolean(rawTurn.usedContext),
    contextSummary: Array.isArray(rawTurn.contextSummary) ? rawTurn.contextSummary.slice(0, 2) : [],
  };
}

function saveSessionMemory() {
  try {
    const payload = {
      version: sessionMemoryVersion,
      activeTurnId: state.activeTurnId,
      turns: state.turns
        .filter((turn) => turn.status !== "pending")
        .map(sanitizeTurnForStorage)
        .filter(Boolean),
    };
    window.sessionStorage.setItem(sessionMemoryKey, JSON.stringify(payload));
  } catch (_error) {
    // Storage can be unavailable in private or restricted browser modes.
  }
}

function sanitizeTurnForStorage(turn) {
  if (!turn || !turn.question) return null;
  return {
    id: turn.id,
    question: String(turn.question).slice(0, 1000),
    status: turn.status === "pending" ? "error" : turn.status,
    body: turn.body ? sanitizeAnswerBody(turn.body) : null,
    errorMessage: String(turn.errorMessage || "").slice(0, 300),
    feedbackKind: turn.feedbackKind === "helpful" || turn.feedbackKind === "not-helpful" ? turn.feedbackKind : "",
    feedbackId: String(turn.feedbackId || "").slice(0, 120),
    feedbackStatus: turn.feedbackStatus === "saved" || turn.feedbackStatus === "failed" ? turn.feedbackStatus : "",
    usedContext: Boolean(turn.usedContext),
    contextSummary: Array.isArray(turn.contextSummary) ? turn.contextSummary.slice(0, 2) : [],
  };
}

function sanitizeAnswerBody(body) {
  const answer = body?.answer || {};
  const retrieve = body?.retrieve || {};
  const route = body?.route || {};
  return {
    schema_version: body?.schema_version || "qa_answer.v1",
    build_id: body?.build_id || "",
    kb_name: body?.kb_name || "",
    trace_id: body?.trace_id || "",
    plan_id: body?.plan_id || "",
    question: body?.question || "",
    route: sanitizeRoute(route),
    answer: {
      kind: answer.kind || "unknown",
      text: String(answer.text || "").slice(0, 4000),
      confidence: typeof answer.confidence === "number" ? answer.confidence : null,
      citations: Array.isArray(answer.citations) ? answer.citations.slice(0, 8) : [],
      refusal_reason: answer.refusal_reason || null,
      missing_evidence_hints: Array.isArray(answer.missing_evidence_hints) ? answer.missing_evidence_hints.slice(0, 5) : [],
      warnings: Array.isArray(answer.warnings) ? answer.warnings.slice(0, 5) : [],
    },
    retrieve: {
      build_id: retrieve.build_id || "",
      kb_name: retrieve.kb_name || "",
      trace_id: retrieve.trace_id || "",
      search_id: retrieve.search_id || "",
      retrieve_id: retrieve.retrieve_id || "",
      plan_id: retrieve.plan_id || "",
      results: Array.isArray(retrieve.results) ? retrieve.results.slice(0, 8).map(sanitizeResult) : [],
      evidence: Array.isArray(retrieve.evidence) ? retrieve.evidence.slice(0, 8).map(sanitizeEvidence) : [],
      context_pack: sanitizeContextPack(retrieve.context_pack),
    },
  };
}

function sanitizeRoute(route) {
  if (!route || typeof route !== "object") return {};
  return {
    kind: route.kind || "",
    reason: route.reason || "",
    candidates: Array.isArray(route.candidates) ? route.candidates.slice(0, 5) : [],
  };
}

function sanitizeEvidence(item) {
  const provenance = sanitizeEvidenceProvenance(item?.provenance || {});
  const assets = Array.isArray(item?.assets) ? item.assets.slice(0, 3).map(sanitizeEvidenceAsset).filter(Boolean) : [];
  return {
    evidence_id: item?.evidence_id || "",
    citation_id: item?.citation_id || "",
    context_item_id: item?.context_item_id || "",
    text: String(item?.text || item?.content || "").slice(0, 1800),
    source: provenance.display_source || item?.source || item?.source_file || "",
    source_file: item?.source_file || item?.source || provenance.source_file || "",
    section_path: Array.isArray(item?.section_path) ? item.section_path.slice(0, 6) : [],
    confidence: typeof item?.confidence === "number" ? item.confidence : null,
    page_range: Array.isArray(item?.page_range) ? item.page_range.slice(0, 2) : [],
    assets,
    asset_warnings: Array.isArray(item?.asset_warnings) ? item.asset_warnings.slice(0, 5).map(safeAssetWarning).filter(Boolean) : [],
    provenance,
    retrieval_reason: item?.retrieval_reason || "",
  };
}

function safeAssetWarning(value) {
  const warning = String(value || "").trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "_").slice(0, 80);
  return warning || "";
}

function sanitizeEvidenceProvenance(provenance) {
  const pageRange = Array.isArray(provenance?.page_range)
    ? provenance.page_range.slice(0, 2).map((item) => Number(item)).filter(Number.isFinite)
    : [];
  return {
    source_format: String(provenance?.source_format || "").slice(0, 32),
    source_file: String(provenance?.source_file || "").slice(0, 180),
    original_source_file: String(provenance?.original_source_file || "").slice(0, 180),
    display_source: String(provenance?.display_source || "").slice(0, 180),
    page_range: pageRange,
    parser_profile: String(provenance?.parser_profile || "").slice(0, 80),
    ocr: Boolean(provenance?.ocr),
    confidence: typeof provenance?.confidence === "number" ? provenance.confidence : null,
  };
}

function sanitizeEvidenceAsset(asset) {
  const url = safeAssetUrl(asset?.url || "");
  if (!url) return null;
  return {
    asset_id: String(asset?.asset_id || "").slice(0, 120),
    type: String(asset?.type || "").slice(0, 40),
    url,
    mime_type: String(asset?.mime_type || "").slice(0, 80),
    page_number: Number.isFinite(Number(asset?.page_number)) ? Number(asset.page_number) : null,
    alt_text: String(asset?.alt_text || "").slice(0, 180),
  };
}

function safeAssetUrl(rawUrl) {
  const value = String(rawUrl || "").trim();
  if (!value.startsWith("/assets/")) return "";
  if (value.includes("\\") || value.includes("//")) return "";
  return value.slice(0, 320);
}

function sanitizeResult(item) {
  return {
    anchor_key: item?.anchor_key || "",
    source_file: item?.source_file || "",
    header: item?.header || "",
    manual_id: item?.manual_id || item?.metadata?.manual_id || "",
  };
}

function sanitizeContextPack(contextPack) {
  const items = Array.isArray(contextPack?.items) ? contextPack.items : [];
  return {
    items: items.slice(0, 8).map((item) => ({
      context_item_id: item?.context_item_id || "",
      evidence_refs: Array.isArray(item?.evidence_refs) ? item.evidence_refs.slice(0, 8) : [],
    })),
  };
}

function clearSessionMemory() {
  try {
    window.sessionStorage.removeItem(sessionMemoryKey);
  } catch (_error) {
    // Ignore storage failures; in-memory history still works.
  }
}

function renderContextNotice(context) {
  const existing = document.getElementById("qa-context-notice");
  if (existing) existing.remove();
  const applied = Boolean(context?.applied);
  const summary = Array.isArray(context?.summary) ? context.summary : [];
  if (!applied || summary.length === 0) return;
  const notice = document.createElement("section");
  notice.id = "qa-context-notice";
  notice.className = "qa-context-notice";
  notice.setAttribute("aria-label", "Conversation context");
  const question = summary.map((item) => item.question).filter(Boolean)[0] || "previous question";
  notice.innerHTML = `
    <strong>${t("Continuing from earlier")}</strong>
    <p>${t("Using context from: {question}", { question: escapeHtml(question) })}</p>
  `;
  el.answer.insertAdjacentElement("afterend", notice);
}

function updateSubmitNewState() {
  if (!el.submitNew) return;
  const question = el.question ? el.question.value.trim() : "";
  el.submitNew.disabled = !shouldUseConversationContext(question);
}

function historyStatusLabel(status) {
  if (status === "pending") return t("Asking...");
  if (status === "answered") return t("Answered");
  if (status === "clarification") return t("Needs detail");
  if (status === "error") return t("Failed");
  return t("No answer");
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
    updateSubmitNewState();
    return;
  }
  if (turn.status === "error") {
    renderError({ message: turn.errorMessage || t("Answer request failed.") });
    updateSubmitNewState();
    return;
  }
  if (turn.body) {
    renderAnswer(turn.body);
  }
  updateSubmitNewState();
}

function clearHistory() {
  state.turns = [];
  state.activeTurnId = "";
  renderHistory();
  clearSessionMemory();
  updateSubmitNewState();
}

function renderSuggestions() {
  if (!el.suggestions) return;
  const questions = state.dynamicSuggestions.length ? state.dynamicSuggestions : suggestedQuestions;
  el.suggestions.innerHTML = questions
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

function renderFirstRunGuidance() {
  if (!el.answer || state.turns.length > 0 || state.kbReady) return;
  el.answer.className = "qa-answer-message empty-state qa-first-run";
  el.answer.innerHTML = `
    <strong>${t("Start by adding a manual")}</strong>
    <p>${t("This knowledge base does not have searchable manual content yet. Add a manual on the left, wait for indexing, then ask your first question here.")}</p>
    <div class="qa-first-run-actions">
      <button type="button" class="ghost small" data-qa-focus-upload>${t("Choose a manual")}</button>
      <a class="button-link compact" href="/admin/rag-readiness?kb_name=${encodeURIComponent(state.kbName || "default")}">${t("Check readiness")}</a>
    </div>
  `;
  const button = el.answer.querySelector("[data-qa-focus-upload]");
  if (button) {
    button.addEventListener("click", () => {
      el.uploadFile?.focus();
      el.uploadForm?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }
  if (el.answerMeta) el.answerMeta.textContent = t("Add a manual to begin");
  if (el.sourceMeta) el.sourceMeta.textContent = t("Sources appear after indexing and Q&A.");
}

function uploadHeaders(json = true) {
  const out = json ? { "Content-Type": "application/json" } : {};
  return { ...out, ...authHeadersFromToken(el.token ? el.token.value : "") };
}

function uploadMetadataFromForm() {
  const title = el.uploadTitle ? el.uploadTitle.value.trim() : "";
  const sourceFile = el.uploadSource ? el.uploadSource.value.trim() : "";
  return {
    manual_id: manualIdFromSource(sourceFile || title || "manual"),
    title,
    source_file: sourceFile,
    product_category: el.uploadCategory ? el.uploadCategory.value.trim() : "",
    language: el.uploadLanguage ? el.uploadLanguage.value.trim() || "unknown" : "unknown",
    tags: tagsFromText(el.uploadTags ? el.uploadTags.value : ""),
  };
}

function tagsFromText(value) {
  return String(value || "")
    .split(/[,\n]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function manualIdFromSource(value) {
  return String(value || "manual")
    .split("/")
    .pop()
    .replace(/\.[^.]+$/, "")
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80) || `manual-${Date.now()}`;
}

function sourcePathFromFileName(fileName) {
  const safeName = String(fileName || "manual.md")
    .trim()
    .replaceAll("\\", "/")
    .split("/")
    .pop()
    .replace(/[^A-Za-z0-9._\-\u4e00-\u9fff]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return `uploads/${safeName || "manual.md"}`;
}

function titleFromFileName(fileName) {
  const stem = String(fileName || "")
    .split("/")
    .pop()
    .replace(/\.[^.]+$/, "")
    .replace(/[-_]+/g, " ")
    .trim();
  return stem ? stem.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "";
}

function applyUploadFileDefaults() {
  const file = el.uploadFile?.files?.[0];
  if (!file) return;
  if (el.uploadTitle && !el.uploadTitle.value.trim()) {
    el.uploadTitle.value = titleFromFileName(file.name);
  }
  if (el.uploadSource && !el.uploadSource.value.trim()) {
    el.uploadSource.value = sourcePathFromFileName(file.name);
  }
  if (el.uploadCategory && !el.uploadCategory.value.trim()) {
    el.uploadCategory.value = "manual";
  }
  if (el.uploadLanguage && !el.uploadLanguage.value.trim()) {
    el.uploadLanguage.value = "zh-CN";
  }
  setUploadMessage(t("Review the details, then upload and index."), "");
}

function setUploadMessage(message, kind = "") {
  if (!el.uploadMessages) return;
  el.uploadMessages.className = kind ? `qa-upload-messages ${kind}` : "qa-upload-messages";
  el.uploadMessages.textContent = message ? t(message) : "";
}

function setUploadRecoveryMessage(message) {
  if (!el.uploadMessages) return;
  const readinessHref = `/admin/rag-readiness?kb_name=${encodeURIComponent(state.kbName || "default")}`;
  const libraryHref = `/admin/manual-library?kb_name=${encodeURIComponent(state.kbName || "default")}`;
  el.uploadMessages.className = "qa-upload-messages error";
  el.uploadMessages.innerHTML = `
    <span>${escapeHtml(t(message))}</span>
    <span class="qa-upload-recovery-links">
      <a href="${readinessHref}">${t("Check readiness")}</a>
      <a href="${libraryHref}">${t("Open Manual Library")}</a>
    </span>
  `;
}

function formatApiError(errorBody, fallback) {
  const detail = errorBody?.detail;
  if (detail && Array.isArray(detail.messages)) {
    return detail.messages.map((item) => `${item.field || "metadata"}: ${item.message}`).join("; ");
  }
  return errorBody?.message || errorBody?.detail || fallback;
}

async function qaApiFetch(path, options = {}) {
  const response = await fetch(`${config.apiBasePath || ""}${path}`, options);
  const text = await response.text();
  let body = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch (_error) {
      body = { message: text };
    }
  }
  if (!response.ok) {
    throw new Error(formatApiError(body, `HTTP ${response.status}`));
  }
  return body;
}

async function validateUploadMetadata(metadata) {
  return qaApiFetch("/manuals/validate", {
    method: "POST",
    headers: uploadHeaders(),
    body: JSON.stringify({ kb_name: state.kbName, metadata, mode: "create" }),
  });
}

async function handleUploadSubmit(event) {
  event.preventDefault();
  const file = el.uploadFile?.files?.[0];
  if (!file) {
    setUploadMessage("Choose a manual file first.", "error");
    el.uploadFile?.focus();
    return;
  }
  const metadata = uploadMetadataFromForm();
  el.uploadSubmit.disabled = true;
  setUploadMessage("Validating manual details...");
  try {
    const validation = await validateUploadMetadata(metadata);
    if (validation && validation.valid === false) {
      setUploadMessage(formatApiError(validation, "Manual details need review."), "error");
      el.uploadSubmit.disabled = false;
      return;
    }
    const form = new FormData();
    form.set("kb_name", state.kbName || "default");
    form.set("metadata", JSON.stringify(metadata));
    form.set("overwrite", "false");
    form.set("trigger_rebuild", "true");
    form.set("file", file);
    const body = await qaApiFetch("/manuals", {
      method: "POST",
      headers: uploadHeaders(false),
      body: form,
    });
    setUploadMessage(body.rebuild_job ? "Manual uploaded. Indexing is queued..." : "Manual uploaded. Indexing started...");
    setStatus(t("Manual uploaded. Indexing it for Q&A..."), "warn");
    if (body.rebuild_job) {
      pollUploadRebuildJob(body.rebuild_job.job_id, metadata);
    } else if (body.rebuild_task) {
      pollUploadRebuild(body.rebuild_task.task_id, metadata);
    } else {
      setUploadMessage("Manual uploaded. Use Advanced if indexing is still required.", "warn");
      el.uploadSubmit.disabled = false;
      await loadKnowledgeBases();
    }
  } catch (error) {
    setUploadMessage(userFacingError(error.message), "error");
    setStatus(userFacingError(error.message), "error");
    el.uploadSubmit.disabled = false;
  }
}

async function pollUploadRebuild(taskId, metadata) {
  if (!taskId) {
    el.uploadSubmit.disabled = false;
    return;
  }
  try {
    const task = await qaApiFetch(`/rebuild/${encodeURIComponent(taskId)}`, {
      headers: uploadHeaders(false),
    });
    if (task.status === "running") {
      setUploadMessage("Indexing manual for Q&A...");
      window.setTimeout(() => pollUploadRebuild(taskId, metadata), 1000);
      return;
    }
    el.uploadSubmit.disabled = false;
    if (task.status === "done") {
      await uploadReady(metadata);
    } else {
      setUploadRecoveryMessage(`Indexing failed: ${task.error || "review RAG Readiness"}`);
      setStatus(t("Indexing needs attention. The previous searchable KB remains available."), "error");
    }
  } catch (error) {
    el.uploadSubmit.disabled = false;
    setUploadMessage(userFacingError(error.message), "error");
  }
}

async function pollUploadRebuildJob(jobId, metadata) {
  if (!jobId) {
    el.uploadSubmit.disabled = false;
    return;
  }
  try {
    const job = await qaApiFetch(`/manual-library/rebuild-jobs/${encodeURIComponent(jobId)}`, {
      headers: uploadHeaders(false),
    });
    if (["queued", "running", "retrying", "cancel_requested"].includes(job.status)) {
      setUploadMessage(job.status === "queued" ? "Indexing is queued..." : "Indexing manual for Q&A...");
      window.setTimeout(() => pollUploadRebuildJob(jobId, metadata), 1000);
      return;
    }
    el.uploadSubmit.disabled = false;
    if (job.status === "succeeded") {
      await uploadReady(metadata);
    } else {
      const detail = job.error?.message || JSON.stringify(job.error || {});
      setUploadRecoveryMessage(`Indexing failed: ${detail || job.status}`);
      setStatus(t("Indexing needs attention. The previous searchable KB remains available."), "error");
    }
  } catch (error) {
    el.uploadSubmit.disabled = false;
    setUploadMessage(userFacingError(error.message), "error");
  }
}

async function uploadReady(metadata) {
  state.kbReady = true;
  state.uploadedManual = metadata || null;
  state.dynamicSuggestions = suggestedQuestionsForManual(metadata);
  await loadKnowledgeBases();
  state.dynamicSuggestions = suggestedQuestionsForManual(metadata);
  renderSuggestions();
  setUploadMessage("Manual is indexed. Ask a question about it below.", "success");
  setStatus(t("Manual is ready for Q&A."), "success");
  if (el.uploadForm) el.uploadForm.reset();
  if (el.question && metadata?.title) {
    el.question.placeholder = t("Ask about {title}", { title: metadata.title });
    el.question.focus();
  }
}

function suggestedQuestionsForManual(metadata) {
  if (!metadata) return [];
  const title = String(metadata.title || "").trim();
  const category = String(metadata.product_category || "").trim();
  const tags = Array.isArray(metadata.tags) ? metadata.tags.map((tag) => String(tag).toLowerCase()) : [];
  const questions = [];
  if (tags.some((tag) => tag.includes("steam")) || title.includes("蒸汽") || category.includes("coffee")) {
    questions.push("这份手册里，蒸汽很小怎么办？");
  }
  if (tags.some((tag) => tag.includes("clean")) || tags.some((tag) => tag.includes("nozzle"))) {
    questions.push("这份手册里，喷嘴怎么清洗？");
  }
  if (tags.some((tag) => tag.includes("service"))) {
    questions.push("这份手册里，服务模式怎么进入？");
  }
  if (title) {
    questions.push(`${title} 有哪些常见故障处理步骤？`);
  }
  questions.push("这份手册里，用户最应该先检查什么？");
  return [...new Set(questions)].slice(0, 4);
}

function renderFollowups(answerText, citations) {
  if (!el.followups) return;
  const questions = buildFollowupQuestions(answerText, citations).slice(0, 3);
  if (questions.length === 0) {
    setHidden(el.followups, true);
    return;
  }
  el.followups.innerHTML = `
    <span class="eyebrow">${t("Suggested follow-ups")}</span>
    <p>${t("These will continue from the current answer when useful.")}</p>
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
  const turn = activeConversationTurn();
  const feedbackKind = turn?.feedbackKind || "";
  el.feedback.querySelectorAll("[data-feedback]").forEach((button) => {
    const selected = button.dataset.feedback === feedbackKind;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
    button.disabled = Boolean(turn?.feedbackPending);
  });
  if (el.feedbackNote) {
    renderFeedbackNote(turn);
  }
}

async function handleFeedback(kind) {
  if (!el.feedback) return;
  const turn = activeConversationTurn();
  if (!turn || !turn.body) return;
  if (turn.feedbackPending) return;
  if (turn.feedbackId && turn.feedbackKind === kind && turn.feedbackStatus === "saved") {
    renderFeedback();
    return;
  }
  updateConversationTurn(turn.id, { feedbackKind: kind, feedbackPending: true, feedbackStatus: "" });
  el.feedback.querySelectorAll("[data-feedback]").forEach((button) => {
    const selected = button.dataset.feedback === kind;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
    button.disabled = true;
  });
  if (el.feedbackNote) {
    el.feedbackNote.textContent = t("Saving feedback...");
  }
  try {
    const response = await fetch("/search/feedback", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(feedbackPayloadForTurn({ ...turn, feedbackKind: kind })),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.message || body.detail || `HTTP ${response.status}`);
    }
    updateConversationTurn(turn.id, {
      feedbackId: body.feedback?.feedback_id || "",
      feedbackPending: false,
      feedbackStatus: "saved",
    });
  } catch (_error) {
    updateConversationTurn(turn.id, {
      feedbackPending: false,
      feedbackStatus: "failed",
    });
  } finally {
    renderFeedback();
  }
}

function activeConversationTurn() {
  return state.turns.find((turn) => turn.id === state.activeTurnId);
}

function feedbackNoteForTurn(turn) {
  if (!turn) return "";
  if (turn.feedbackPending) return t("Saving feedback...");
  if (turn.feedbackStatus === "saved") return t("Feedback sent to Retrieval Quality.");
  if (turn.feedbackStatus === "failed") return t("Feedback could not be saved.");
  return feedbackNoteForKind(turn.feedbackKind || "");
}

function renderFeedbackNote(turn) {
  if (!el.feedbackNote) return;
  el.feedbackNote.replaceChildren();
  const note = feedbackNoteForTurn(turn);
  if (!note) return;
  el.feedbackNote.append(document.createTextNode(note));
  const href = feedbackReviewHref(turn);
  if (!href) return;
  el.feedbackNote.append(document.createTextNode(" "));
  const link = document.createElement("a");
  link.className = "qa-feedback-review-link";
  link.href = href;
  link.textContent = t("Review this case");
  el.feedbackNote.append(link);
}

function feedbackReviewHref(turn) {
  if (!turn || turn.feedbackStatus !== "saved" || !turn.feedbackId) return "";
  const body = turn.body || {};
  const retrieve = body.retrieve || {};
  const params = new URLSearchParams();
  params.set("kb_name", body.kb_name || retrieve.kb_name || state.kbName || "default");
  params.set("feedback_id", turn.feedbackId);
  return `/admin/retrieval-quality?${params.toString()}`;
}

function feedbackNoteForKind(kind) {
  if (kind === "helpful") return t("Marked helpful for this answer.");
  if (kind === "not-helpful") return t("Marked for review in this page session.");
  return "";
}

function feedbackPayloadForTurn(turn) {
  const body = turn.body || {};
  const retrieve = body.retrieve || {};
  const answer = body.answer || {};
  const kind = String(turn.feedbackKind || "");
  const outcome = kind === "not-helpful" ? "not_helpful" : "helpful";
  return {
    kb_name: body.kb_name || retrieve.kb_name || state.kbName || "default",
    trace_id: body.trace_id || retrieve.trace_id || "",
    search_id: retrieve.search_id || "",
    retrieve_id: retrieve.retrieve_id || "",
    build_id: body.build_id || retrieve.build_id || "",
    query: turn.question || body.question || "",
    outcome,
    selected_results: selectedResultsForFeedback(retrieve),
    selected_evidence_ids: selectedEvidenceIdsForFeedback(body),
    selected_context_item_ids: selectedContextItemIdsForFeedback(retrieve),
    answerable: String(answer.kind || "") === "answer",
    failure_reason: String(answer.kind || "") === "answer" ? "" : String(answer.refusal_reason || answer.text || "").slice(0, 120),
    note: `Q&A feedback: ${outcome}`,
    plan_id: body.plan_id || retrieve.plan_id || null,
  };
}

function selectedResultsForFeedback(retrieve) {
  const results = Array.isArray(retrieve?.results) ? retrieve.results : [];
  if (results.length > 0) {
    return results.slice(0, 8).map((item, index) => ({
      rank: index + 1,
      anchor_key: item.anchor_key || "",
      source_file: item.source_file || "",
      header: item.header || "",
      manual_id: item.manual_id || item.metadata?.manual_id || "",
    }));
  }
  const evidence = Array.isArray(retrieve?.evidence) ? retrieve.evidence : [];
  return evidence.slice(0, 8).map((item, index) => ({
    rank: index + 1,
    anchor_key: "",
    source_file: item.source_file || item.source || "",
    header: Array.isArray(item.section_path) ? item.section_path.at(-1) || "" : "",
    manual_id: item.doc_id || "",
  }));
}

function selectedEvidenceIdsForFeedback(body) {
  const answerCitations = Array.isArray(body?.answer?.citations) ? body.answer.citations : [];
  const evidence = Array.isArray(body?.retrieve?.evidence) ? body.retrieve.evidence : [];
  const ids = [
    ...answerCitations.map((item) => item.evidence_id || item.citation_id || item),
    ...evidence.map((item) => item.evidence_id || item.citation_id || ""),
  ].filter(Boolean);
  return [...new Set(ids)].slice(0, 20);
}

function selectedContextItemIdsForFeedback(retrieve) {
  const items = Array.isArray(retrieve?.context_pack?.items) ? retrieve.context_pack.items : [];
  return [...new Set(items.map((item) => item.context_item_id).filter(Boolean))].slice(0, 20);
}

async function copyAnswer() {
  if (!state.lastAnswerText) return;
  try {
    await navigator.clipboard.writeText(state.lastAnswerText);
    setStatus(t("Answer copied."), "success");
  } catch (_error) {
    setStatus(t("Copy failed. Select the answer text to copy it manually."), "error");
  }
}

function confidenceLabel(confidence) {
  if (typeof confidence !== "number") return t("Answer generated from manual evidence");
  if (confidence >= 0.75) return t("High confidence");
  if (confidence >= 0.45) return t("Medium confidence");
  return t("Low confidence");
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
  return `<button class="qa-citation-chip" type="button" data-citation-target="${safeCitation}" aria-label="${t("Show source {citation}", { citation: safeCitation })}">${safeCitation}</button>`;
}

function userFacingReason(reason) {
  const normalized = String(reason || "").replaceAll("_", " ");
  if (normalized === "generation disabled") return "Answer generation is not enabled for this server.";
  if (normalized === "generation failed") return "The answer service could not generate a response.";
  if (normalized === "insufficient evidence") return "I could not find enough manual evidence to answer that.";
  if (normalized === "no results") return "I could not find enough manual evidence to answer that.";
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
    el.sources.innerHTML = `
      <div class="qa-source-placeholder">
        <strong>${t("No cited sources returned.")}</strong>
        <p>${t("Try a more specific product, symptom, task, or error code.")}</p>
      </div>
    `;
    el.sourceMeta.textContent = t("No sources available.");
    return;
  }

  el.sources.className = "qa-source-list";
  el.sourceMeta.textContent = t("{count} source{plural} cited. Click a citation in the answer to focus a source.", { count: items.length, plural: items.length === 1 ? "" : "s" });
  el.sources.innerHTML = items.map(renderSourceItem).join("");
  bindSourceToggles();
  bindCitationLinks();
}

function renderClarificationCandidates(candidates) {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    el.sources.className = "qa-source-list empty-state";
    el.sources.textContent = t("No candidate manuals available.");
    el.sourceMeta.textContent = t("More detail needed.");
    return;
  }
  el.sources.className = "qa-source-list";
  el.sourceMeta.textContent = t("Possible manual contexts");
  el.sources.innerHTML = candidates
    .map((candidate) => `
      <article class="qa-source-item">
        <div class="evidence-head">
          <span>${escapeHtml(candidate.label || candidate.kb_name || t("Manual"))}</span>
        </div>
        <p class="muted">${t("Add the product name, model, or error code to route this question.")}</p>
      </article>
    `)
    .join("");
}

function renderSourceItem(item) {
  const citation = item.citation_id || item.evidence_id || t("source");
  const safeCitation = escapeHtml(citation);
  const source = sourceDisplayName(item);
  const section = Array.isArray(item.section_path) ? item.section_path.join(" / ") : "";
  const text = item.text || item.content || "";
  const summary = summarizeSourceText(text);
  const canExpand = text.length > summary.length;
  const badges = sourceProvenanceBadges(item);
  const verification = renderSourceVerification(item);
  return `
    <article id="qa-source-${safeCitation}" class="qa-source-item" data-citation-id="${safeCitation}">
      <div class="qa-source-card-head">
        <span class="badge">${safeCitation}</span>
        <div>
          <strong>${escapeHtml(source || t("Manual source"))}</strong>
          <small>${escapeHtml(evidenceStrengthLabel(item.confidence))}</small>
        </div>
      </div>
      ${badges.length ? `<div class="qa-source-badges">${badges.map((badge) => `<span class="${badge.className}">${escapeHtml(badge.label)}</span>`).join("")}</div>` : ""}
      ${verification}
      ${section ? `<p class="qa-source-section"><span>${t("Section")}</span>${escapeHtml(section)}</p>` : ""}
      <p class="qa-source-summary">${escapeHtml(summary)}</p>
      ${canExpand ? `<p class="qa-source-full" hidden>${escapeHtml(text)}</p><button class="qa-source-toggle" type="button" data-source-toggle>${t("Show more")}</button>` : ""}
    </article>
  `;
}

function renderSourceVerification(item) {
  const asset = previewAssetForEvidence(item);
  const pageLabel = formatPageRange((item?.provenance || {}).page_range || item?.page_range);
  if (asset) {
    const detail = sourceVerificationDetail(item, asset, pageLabel);
    return `
      <div class="qa-source-verify has-preview">
        <div>
          <strong>${t("Verify original source")}</strong>
          <small>${escapeHtml(detail)}</small>
        </div>
        <a class="qa-source-preview-link" href="${escapeHtml(asset.url)}" target="_blank" rel="noopener" data-source-preview>${t("Open source preview")}</a>
      </div>
    `;
  }
  const fallback = sourcePreviewFallbackDetail(item, pageLabel);
  return `
    <div class="qa-source-verify unavailable" data-source-preview-unavailable>
      <div>
        <strong>${t("Verify original source")}</strong>
        <small>${escapeHtml(fallback)}</small>
      </div>
    </div>
  `;
}

function previewAssetForEvidence(item) {
  const assets = Array.isArray(item?.assets) ? item.assets : [];
  return assets.find((asset) => asset && asset.url && (asset.type === "page_snapshot" || asset.type === "region_crop")) || assets.find((asset) => asset && asset.url) || null;
}

function sourcePreviewFallbackDetail(item, pageLabel) {
  const warnings = Array.isArray(item?.asset_warnings) ? item.asset_warnings : [];
  if (warnings.includes("asset_manifest_missing")) {
    return t("Preview unavailable. Source preview assets have not been built for this knowledge base.");
  }
  if (warnings.includes("asset_failed_renderer_unavailable")) {
    return t("Preview unavailable. The PDF snapshot renderer is missing.");
  }
  if (warnings.some((warning) => String(warning).startsWith("asset_failed_"))) {
    return t("Preview unavailable. PDF snapshot extraction needs review.");
  }
  if (warnings.includes("no_matching_assets") || warnings.includes("visual_asset_missing")) {
    return pageLabel
      ? t("Preview unavailable. Use the cited passage and {page} to verify the source.", { page: pageLabel })
      : t("Preview unavailable. Use the cited passage to verify the source.");
  }
  return pageLabel
    ? t("Preview unavailable. Use the cited passage and {page} to verify the source.", { page: pageLabel })
    : t("Preview unavailable. Use the cited passage to verify the source.");
}

function sourceVerificationDetail(item, asset, pageLabel) {
  const provenance = item?.provenance || {};
  if (provenance.ocr) {
    return pageLabel
      ? t("OCR text should be checked against the page image for {page}.", { page: pageLabel })
      : t("OCR text should be checked against the page image.");
  }
  if (pageLabel) return t("Preview opens the cited source image for {page}.", { page: pageLabel });
  if (asset.page_number) return t("Preview opens source page {page}.", { page: asset.page_number });
  return t("Preview opens the cited source image.");
}

function sourceDisplayName(item) {
  const provenance = item?.provenance || {};
  return provenance.display_source || item?.source || item?.source_file || "";
}

function sourceProvenanceBadges(item) {
  const provenance = item?.provenance || {};
  const badges = [{ label: t("Cited manual passage"), className: "qa-source-badge" }];
  const pageRange = provenance.page_range && provenance.page_range.length ? provenance.page_range : item?.page_range;
  const pageLabel = formatPageRange(pageRange);
  if (pageLabel) badges.push({ label: pageLabel, className: "qa-source-badge" });
  if (provenance.ocr) badges.push({ label: t("OCR text"), className: "qa-source-badge qa-source-badge-ocr" });
  if (provenance.source_format === "docx" && provenance.original_source_file) {
    badges.push({ label: t("Converted from DOCX"), className: "qa-source-badge qa-source-badge-converted" });
  }
  if (provenance.source_file && provenance.original_source_file && provenance.source_file !== provenance.original_source_file) {
    badges.push({ label: t("Indexed as {source}", { source: provenance.source_file }), className: "qa-source-badge qa-source-badge-indexed" });
  }
  return badges;
}

function formatPageRange(pageRange) {
  if (!Array.isArray(pageRange) || pageRange.length === 0) return "";
  const start = Number(pageRange[0]);
  const end = Number(pageRange[1] ?? pageRange[0]);
  if (!Number.isFinite(start)) return "";
  if (!Number.isFinite(end) || end === start) return t("Page {page}", { page: start });
  return t("Pages {start}-{end}", { start, end });
}

function evidenceStrengthLabel(confidence) {
  if (typeof confidence !== "number") return t("Evidence strength unknown");
  if (confidence >= 0.75) return t("Strong evidence");
  if (confidence >= 0.45) return t("Moderate evidence");
  return t("Weak evidence");
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
      button.textContent = expanding ? t("Show less") : t("Show more");
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
  el.sources.querySelectorAll(".qa-source-item.active, .qa-source-item.pulse").forEach((item) => {
    item.classList.remove("active", "pulse");
  });
  source.classList.add("active", "pulse");
  window.setTimeout(() => source.classList.remove("pulse"), 1400);
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
if (el.submitNew) el.submitNew.addEventListener("click", requestNewQuestion);
if (el.question) el.question.addEventListener("input", updateSubmitNewState);
if (el.kbSelect) el.kbSelect.addEventListener("change", handleKbSelection);
if (el.uploadFile) el.uploadFile.addEventListener("change", applyUploadFileDefaults);
if (el.uploadForm) el.uploadForm.addEventListener("submit", handleUploadSubmit);
bindSharedApiToken(el.token);
initI18n({ mount: ".qa-left-rail" });
updateLinks();
renderSuggestions();
loadKnowledgeBases();
loadSessionMemory();
renderHistory();
if (state.activeTurnId) restoreConversationTurn(state.activeTurnId);
applyQuestionPrefill();
updateSubmitNewState();
updateLocationKb();
translatePage();
