const configEl = document.getElementById("qa-page-config");
const config = configEl ? JSON.parse(configEl.textContent || "{}") : {};

const state = {
  kbName: config.defaultKbName || "default",
};

const el = {
  token: document.getElementById("qa-api-token"),
  questionForm: document.getElementById("qa-question-form"),
  question: document.getElementById("qa-question"),
  submit: document.getElementById("qa-submit"),
  status: document.getElementById("qa-status"),
  answerMeta: document.getElementById("qa-answer-meta"),
  answer: document.getElementById("qa-answer"),
  sourceMeta: document.getElementById("qa-source-meta"),
  sources: document.getElementById("qa-sources"),
  contextNote: document.getElementById("qa-context-note"),
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function updateLocationKb() {
  const nextUrl = new URL(window.location.href);
  nextUrl.searchParams.set("kb_name", state.kbName || "default");
  window.history.replaceState({}, "", nextUrl);
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

  updateLocationKb();
  renderPending();
  el.submit.disabled = true;
  setStatus("Asking...");

  try {
    const response = await fetch("/answer", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        kb_name: state.kbName,
        question,
        top_k: 5,
        source_k: 8,
        mode: "classic",
        include_retrieve: true,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.message || body.detail || `HTTP ${response.status}`);
    }
    renderAnswer(body);
    setStatus("Answer ready.", "success");
  } catch (error) {
    renderError(error);
    setStatus(userFacingError(error.message), "error");
  } finally {
    el.submit.disabled = false;
  }
}

function renderPending() {
  el.answer.className = "qa-answer-message empty-state";
  el.answer.textContent = "Waiting for answer...";
  el.answerMeta.textContent = "Searching the selected knowledge base";
  el.sources.className = "qa-source-list empty-state";
  el.sources.textContent = "Looking for sources...";
  el.sourceMeta.textContent = "Cited source snippets will appear here.";
}

function renderError(error) {
  el.answer.className = "qa-answer-message error";
  el.answer.textContent = userFacingError(error.message);
  el.answerMeta.textContent = "Request failed";
  el.sources.className = "qa-source-list empty-state";
  el.sources.textContent = "No sources available.";
  el.sourceMeta.textContent = "Sources unavailable.";
}

function renderAnswer(body) {
  const answer = body.answer || {};
  const retrieve = body.retrieve || {};
  const kind = String(answer.kind || "unknown");

  if (kind === "answer") {
    el.answer.className = "qa-answer-message";
    el.answer.innerHTML = `<p>${escapeHtml(answer.text || "")}</p>`;
    el.answerMeta.textContent = confidenceLabel(answer.confidence);
  } else {
    el.answer.className = "qa-answer-message warn";
    const reason = answer.refusal_reason || "I could not answer from the available manual content.";
    const hints = Array.isArray(answer.missing_evidence_hints) ? answer.missing_evidence_hints : [];
    el.answer.innerHTML = [
      `<p>${escapeHtml(userFacingReason(reason))}</p>`,
      ...hints.map((hint) => `<p class="muted">${escapeHtml(hint)}</p>`),
    ].join("");
    el.answerMeta.textContent = "No grounded answer available";
  }

  renderSources(answer.citations || [], retrieve.evidence || []);
}

function confidenceLabel(confidence) {
  if (typeof confidence !== "number") return "Answer generated from manual evidence";
  if (confidence >= 0.75) return "High confidence";
  if (confidence >= 0.45) return "Medium confidence";
  return "Low confidence";
}

function userFacingReason(reason) {
  const normalized = String(reason || "").replaceAll("_", " ");
  if (normalized === "generation disabled") return "Answer generation is not enabled for this server.";
  if (normalized === "generation failed") return "The answer service could not generate a response.";
  if (normalized === "insufficient evidence") return "I could not find enough manual evidence to answer that.";
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
}

function renderSourceItem(item) {
  const citation = item.citation_id || item.evidence_id || "source";
  const source = item.source || item.source_file || "";
  const section = Array.isArray(item.section_path) ? item.section_path.join(" / ") : "";
  const text = item.text || item.content || "";
  return `
    <article class="qa-source-item">
      <div class="evidence-head">
        <span class="badge">${escapeHtml(citation)}</span>
        <span class="muted">${escapeHtml(source)}</span>
      </div>
      ${section ? `<p class="muted">${escapeHtml(section)}</p>` : ""}
      <p>${escapeHtml(text)}</p>
    </article>
  `;
}

el.questionForm.addEventListener("submit", requestAnswer);
updateLocationKb();
