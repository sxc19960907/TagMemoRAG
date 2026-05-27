import { authHeadersFromToken, bindSharedApiToken } from "./admin_token.js";
import { initI18n, t, translatePage } from "./i18n.js";

const configEl = document.getElementById("rag-workbench-config");
const config = configEl ? JSON.parse(configEl.textContent || "{}") : {};

const state = {
  kbName: config.defaultKbName || "default",
  loading: false,
};

const el = {
  kbForm: document.getElementById("workbench-kb-form"),
  kbName: document.getElementById("workbench-kb-name"),
  token: document.getElementById("workbench-api-token"),
  status: document.getElementById("workbench-status"),
  questionForm: document.getElementById("workbench-question-form"),
  question: document.getElementById("workbench-question"),
  topK: document.getElementById("workbench-top-k"),
  sourceK: document.getElementById("workbench-source-k"),
  mode: document.getElementById("workbench-mode"),
  submit: document.getElementById("workbench-submit"),
  answer: document.getElementById("workbench-answer"),
  answerMeta: document.getElementById("workbench-answer-meta"),
  citations: document.getElementById("workbench-citations"),
  traceSummary: document.getElementById("workbench-trace-summary"),
  warnings: document.getElementById("workbench-warnings"),
  answerability: document.getElementById("workbench-answerability"),
  evidence: document.getElementById("workbench-evidence"),
  results: document.getElementById("workbench-results"),
  manualLibrary: document.getElementById("workbench-manual-library"),
  retrievalQuality: document.getElementById("workbench-retrieval-quality"),
  evalReport: document.getElementById("workbench-eval-report"),
  readiness: document.getElementById("workbench-readiness"),
  people: document.getElementById("workbench-people"),
  qa: document.getElementById("workbench-qa"),
};

function headers() {
  const out = { "Content-Type": "application/json" };
  return { ...out, ...authHeadersFromToken(el.token.value) };
}

function setStatus(message, kind = "") {
  el.status.textContent = message ? t(message) : "";
  el.status.className = kind ? `status-strip ${kind}` : "status-strip";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function updateLinks() {
  const kb = encodeURIComponent(state.kbName || "default");
  el.manualLibrary.href = `/admin/manual-library?kb_name=${kb}`;
  el.retrievalQuality.href = `/admin/retrieval-quality?kb_name=${kb}`;
  el.evalReport.href = `/admin/eval-report?kb_name=${kb}`;
  el.readiness.href = `/admin/rag-readiness?kb_name=${kb}`;
  el.people.href = `/admin/people?kb_name=${kb}`;
  el.qa.href = `/qa?kb_name=${kb}`;
}

async function requestAnswer(event) {
  event.preventDefault();
  const question = el.question.value.trim();
  if (!question) {
    setStatus(t("Enter a question first."), "error");
    return;
  }
  state.kbName = el.kbName.value.trim() || "default";
  updateLinks();
  const payload = {
    kb_name: state.kbName,
    question,
    top_k: Number(el.topK.value || 5),
    source_k: Number(el.sourceK.value || 8),
    mode: el.mode.value,
    include_retrieve: true,
  };
  state.loading = true;
  el.submit.disabled = true;
  setStatus(t("Asking..."), "");
  renderPending();
  try {
    const response = await fetch("/answer", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.message || body.detail || `HTTP ${response.status}`);
    }
    renderAnswer(body);
    setStatus(t("Answer loaded."), "success");
  } catch (error) {
    renderError(error);
    setStatus(error.message || t("Answer request failed."), "error");
  } finally {
    state.loading = false;
    el.submit.disabled = false;
  }
}

function renderPending() {
  el.answer.className = "answer-body empty-state";
  el.answer.textContent = t("Waiting for answer...");
  el.citations.innerHTML = "";
  el.evidence.className = "evidence-list empty-state";
  el.evidence.textContent = t("Waiting for evidence...");
  el.results.className = "evidence-list empty-state";
  el.results.textContent = t("Waiting for results...");
  el.warnings.innerHTML = "";
  el.answerMeta.textContent = t("Request in progress");
  el.traceSummary.textContent = "";
  el.answerability.textContent = "";
}

function renderError(error) {
  el.answer.className = "answer-body error";
  el.answer.textContent = error.message || t("Request failed");
  el.answerMeta.textContent = t("Request failed");
  el.citations.innerHTML = "";
  el.evidence.className = "evidence-list empty-state";
  el.evidence.textContent = t("No evidence loaded.");
  el.results.className = "evidence-list empty-state";
  el.results.textContent = t("No results loaded.");
}

function renderAnswer(body) {
  const answer = body.answer || {};
  const retrieve = body.retrieve || {};
  const answerKind = String(answer.kind || "unknown");
  el.answer.className = `answer-body ${answerKind === "answer" ? "" : "warn"}`;
  if (answerKind === "answer") {
    el.answer.innerHTML = `<p>${escapeHtml(answer.text || "")}</p>`;
  } else {
    const reason = answer.refusal_reason || "answer_not_available";
    const hints = Array.isArray(answer.missing_evidence_hints) ? answer.missing_evidence_hints.join(", ") : "";
    el.answer.innerHTML = `<p>${escapeHtml(reason)}</p>${hints ? `<p class="muted">${escapeHtml(hints)}</p>` : ""}`;
  }
  const model = answer.model_id ? `model=${answer.model_id}` : "model=";
  el.answerMeta.textContent = `kind=${answerKind} | ${model}`;
  renderCitations(answer.citations || []);
  renderWarnings(body.warnings || []);
  renderTrace(body, retrieve);
  renderAnswerability(retrieve.answerability || {});
  renderEvidence(retrieve.evidence || []);
  renderResults(retrieve.results || []);
}

function renderCitations(citations) {
  if (!Array.isArray(citations) || citations.length === 0) {
    el.citations.innerHTML = `<span class="muted">${t("No answer citations.")}</span>`;
    return;
  }
  el.citations.innerHTML = citations
    .map((citation) => `<span class="badge">${escapeHtml(citation.citation_id || citation)}</span>`)
    .join("");
}

function renderWarnings(warnings) {
  if (!Array.isArray(warnings) || warnings.length === 0) {
    el.warnings.innerHTML = `<span class="muted">${t("No warnings.")}</span>`;
    return;
  }
  el.warnings.innerHTML = warnings.map((warning) => `<span class="badge warn">${escapeHtml(warning)}</span>`).join("");
}

function renderTrace(body, retrieve) {
  const planId = body.plan_id || retrieve.plan_id || "";
  const buildId = body.build_id || retrieve.build_id || "";
  el.traceSummary.textContent = `plan=${planId || "-"} | build=${buildId || "-"} | schema=${body.schema_version || "-"}`;
}

function renderAnswerability(answerability) {
  if (!answerability || Object.keys(answerability).length === 0) {
    el.answerability.textContent = "No answerability summary";
    return;
  }
  const answerable = answerability.answerable === true ? t("answerable") : t("not answerable");
  const reason = answerability.reason || "";
  el.answerability.textContent = `${answerable}${reason ? ` | ${reason}` : ""}`;
}

function renderEvidence(evidence) {
  if (!Array.isArray(evidence) || evidence.length === 0) {
    el.evidence.className = "evidence-list empty-state";
    el.evidence.textContent = t("No evidence returned.");
    return;
  }
  el.evidence.className = "evidence-list";
  el.evidence.innerHTML = evidence.map(renderEvidenceItem).join("");
}

function renderResults(results) {
  if (!Array.isArray(results) || results.length === 0) {
    el.results.className = "evidence-list empty-state";
    el.results.textContent = t("No results returned.");
    return;
  }
  el.results.className = "evidence-list";
  el.results.innerHTML = results.map(renderResultItem).join("");
}

function renderEvidenceItem(item) {
  const citation = item.citation_id || item.evidence_id || "";
  const source = item.source || item.source_file || "";
  const text = item.text || item.content || "";
  return `
    <article class="evidence-item">
      <div class="evidence-head">
        <span class="badge">${escapeHtml(citation)}</span>
        <span class="muted">${escapeHtml(source)}</span>
      </div>
      <p>${escapeHtml(text)}</p>
    </article>
  `;
}

function renderResultItem(item) {
  const score = Number(item.score || 0).toFixed(3);
  const title = item.header || item.path || item.source_file || t("Result");
  return `
    <article class="evidence-item">
      <div class="evidence-head">
        <span>${escapeHtml(title)}</span>
        <span class="muted">score=${score}</span>
      </div>
      <p>${escapeHtml(item.text || "")}</p>
    </article>
  `;
}

function applyQuestionPrefill() {
  const params = new URLSearchParams(window.location.search);
  const question = params.get("question") || "";
  if (!question) return;
  el.question.value = question;
  setStatus(t("Question prefilled. Review it, then ask when ready."), "success");
}

el.kbForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.kbName = el.kbName.value.trim() || "default";
  updateLinks();
  setStatus(`KB set to ${state.kbName}.`);
});

el.questionForm.addEventListener("submit", requestAnswer);
bindSharedApiToken(el.token);
initI18n({ mount: ".workbench-links" });
updateLinks();
applyQuestionPrefill();
translatePage();
