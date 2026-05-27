import { authHeadersFromToken, bindSharedApiToken } from "./admin_token.js";
import { initI18n, t, translatePage } from "./i18n.js";

const config = JSON.parse(document.getElementById("rag-readiness-config").textContent);

const state = {
  kbName: config.defaultKbName || "default",
  summary: null,
};

const el = {
  form: document.getElementById("readiness-kb-form"),
  kbName: document.getElementById("readiness-kb-name"),
  token: document.getElementById("readiness-api-token"),
  status: document.getElementById("readiness-status"),
  state: document.getElementById("readiness-state"),
  title: document.getElementById("readiness-title"),
  summary: document.getElementById("readiness-summary"),
  actions: document.getElementById("readiness-actions"),
  cards: document.getElementById("readiness-cards"),
  recommendationCount: document.getElementById("readiness-recommendation-count"),
  recommendations: document.getElementById("readiness-recommendations"),
  refresh: document.getElementById("readiness-refresh"),
  workbench: document.getElementById("readiness-workbench"),
  manualLibrary: document.getElementById("readiness-manual-library"),
  retrievalQuality: document.getElementById("readiness-retrieval-quality"),
  evalReport: document.getElementById("readiness-eval-report"),
  qa: document.getElementById("readiness-qa"),
};

function tokenHeaders() {
  return authHeadersFromToken(el.token.value);
}

function apiPath(path) {
  return `${config.apiBasePath || ""}${path}`;
}

function setStatus(message, kind = "") {
  el.status.textContent = message ? t(message) : "";
  el.status.className = kind ? `status-strip ${kind}` : "status-strip";
}

function updateLinks() {
  const kb = encodeURIComponent(state.kbName || "default");
  el.workbench.href = `/admin/rag-workbench?kb_name=${kb}`;
  el.manualLibrary.href = `/admin/manual-library?kb_name=${kb}`;
  el.retrievalQuality.href = `/admin/retrieval-quality?kb_name=${kb}`;
  el.evalReport.href = `/admin/eval-report?kb_name=${kb}`;
  el.qa.href = `/qa?kb_name=${kb}`;
}

async function requestJson(path) {
  const response = await fetch(apiPath(path), {
    headers: {
      "Content-Type": "application/json",
      ...tokenHeaders(),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.message || body.code || `HTTP ${response.status}`);
  }
  return body;
}

async function loadReadiness() {
  state.kbName = el.kbName.value.trim() || "default";
  updateLinks();
  setStatus(t("Loading readiness signals..."));
  const body = await requestJson(`/admin/rag-readiness/summary?kb_name=${encodeURIComponent(state.kbName)}`);
  state.summary = body;
  renderSummary(body);
  setStatus(t("Readiness loaded."), "success");
}

function renderSummary(body) {
  const status = body.status || "unknown";
  el.state.className = `status-pill ${statusClass(status)}`;
  el.state.textContent = t(statusLabel(status));
  el.title.textContent = `${t("RAG Readiness")} · ${body.kb_name || state.kbName}`;
  el.summary.textContent = t(body.summary || "");
  renderActions(body.actions || []);
  renderCards(body.cards || []);
  renderRecommendations(body.recommendations || []);
}

function renderActions(actions) {
  if (!Array.isArray(actions) || !actions.length) {
    el.actions.innerHTML = "";
    return;
  }
  el.actions.innerHTML = actions.map((action) => `
    <a class="button-link ${action.kind === "primary" ? "primary-link" : ""}" href="${escapeHtml(action.href || "#")}">${escapeHtml(t(action.label || "Open"))}</a>
  `).join("");
}

function renderCards(cards) {
  if (!Array.isArray(cards) || !cards.length) {
    el.cards.className = "readiness-card-grid empty-state";
    el.cards.textContent = t("No readiness checks returned.");
    return;
  }
  el.cards.className = "readiness-card-grid";
  el.cards.innerHTML = cards.map(renderCard).join("");
}

function renderCard(card) {
  const detail = card.detail || {};
  const detailRows = Object.entries(detail)
    .filter(([, value]) => typeof value !== "object" || value === null)
    .map(([key, value]) => `<dt>${escapeHtml(humanizeKey(key))}</dt><dd>${escapeHtml(formatValue(value))}</dd>`)
    .join("");
  return `
    <article class="readiness-card ${escapeHtml(card.status || "unknown")}">
      <span class="status-pill ${statusClass(card.status)}">${escapeHtml(t(statusLabel(card.status)))}</span>
      <h3>${escapeHtml(t(card.title || "Readiness check"))}</h3>
      <p>${escapeHtml(t(card.summary || ""))}</p>
      ${detailRows ? `<dl>${detailRows}</dl>` : ""}
    </article>
  `;
}

function renderRecommendations(recommendations) {
  const items = Array.isArray(recommendations) ? recommendations : [];
  el.recommendationCount.textContent = items.length ? `${items.length} ${t("recommendations")}` : t("No recommendations.");
  if (!items.length) {
    el.recommendations.className = "readiness-recommendations empty-state";
    el.recommendations.textContent = t("No recommendations.");
    return;
  }
  el.recommendations.className = "readiness-recommendations";
  el.recommendations.innerHTML = items.map((item) => `
    <article class="readiness-recommendation ${escapeHtml(item.severity || "info")}">
      <span class="status-pill ${item.severity === "error" ? "needs-review" : item.severity === "warning" ? "in-progress" : "neutral"}">${escapeHtml(t(item.severity || "info"))}</span>
      <p>${escapeHtml(t(item.label || ""))}</p>
    </article>
  `).join("");
}

function statusClass(status) {
  if (status === "ready") return "good";
  if (status === "not_ready") return "needs-review";
  if (status === "needs_review") return "in-progress";
  return "neutral";
}

function statusLabel(status) {
  if (status === "ready") return "Ready";
  if (status === "not_ready") return "Not ready";
  if (status === "needs_review") return "Needs review";
  return "Unknown";
}

function humanizeKey(key) {
  return String(key || "").replaceAll("_", " ");
}

function formatValue(value) {
  if (value === true) return t("Yes");
  if (value === false) return t("No");
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

el.form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadReadiness().catch((error) => setStatus(error.message, "error"));
});
el.refresh.addEventListener("click", () => {
  loadReadiness().catch((error) => setStatus(error.message, "error"));
});

bindSharedApiToken(el.token);
initI18n({ mount: ".readiness-links" });
updateLinks();
loadReadiness().catch((error) => setStatus(error.message, "error"));
translatePage();
