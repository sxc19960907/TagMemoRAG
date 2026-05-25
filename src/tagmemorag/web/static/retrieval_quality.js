import { authHeadersFromToken, bindSharedApiToken } from "./admin_token.js";

const config = JSON.parse(document.getElementById("retrieval-quality-config").textContent);

const state = {
  rows: [],
  selectedId: null,
};

const $ = (id) => document.getElementById(id);

function tokenHeaders() {
  return authHeadersFromToken($("quality-api-token").value);
}

function apiPath(path) {
  return `${config.apiBasePath || ""}${path}`;
}

function setStatus(message, kind = "") {
  const node = $("quality-status");
  node.textContent = message;
  node.className = `status-strip ${kind}`.trim();
}

async function requestJson(path, options = {}) {
  const response = await fetch(apiPath(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...tokenHeaders(),
      ...(options.headers || {}),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.message || body.code || `HTTP ${response.status}`);
  }
  return body;
}

function currentKb() {
  return $("quality-kb-name").value.trim() || config.defaultKbName || "default";
}

async function loadFeedback() {
  const params = new URLSearchParams({ kb_name: currentKb(), limit: $("quality-filter-limit").value || "50" });
  for (const [key, id] of [
    ["status", "quality-filter-status"],
    ["outcome", "quality-filter-outcome"],
    ["query", "quality-filter-query"],
  ]) {
    const value = $(id).value.trim();
    if (value) params.set(key, value);
  }
  setStatus("Loading feedback...");
  const body = await requestJson(`/search/feedback?${params.toString()}`, { method: "GET" });
  state.rows = body.feedback || [];
  state.selectedId = state.rows.some((row) => row.feedback_id === state.selectedId) ? state.selectedId : null;
  renderRows();
  renderDetail();
  setStatus(`Loaded ${state.rows.length} feedback records.`, "success");
}

function renderRows() {
  const tbody = $("quality-feedback-rows");
  tbody.innerHTML = "";
  for (const row of state.rows) {
    const tr = document.createElement("tr");
    tr.dataset.feedbackId = row.feedback_id;
    if (row.feedback_id === state.selectedId) tr.classList.add("selected-row");
    tr.innerHTML = `
      <td><input type="checkbox" data-select-feedback="${escapeHtml(row.feedback_id)}"></td>
      <td>${escapeHtml((row.created_at || "").slice(0, 19))}</td>
      <td><span class="status-pill">${escapeHtml(row.outcome)}</span></td>
      <td><span class="status-pill">${escapeHtml(row.status)}</span></td>
      <td class="query-cell">${escapeHtml(row.query)}</td>
      <td>${escapeHtml(row.build_id || "")}</td>
      <td>${escapeHtml(refSummary(row))}</td>
    `;
    tr.addEventListener("click", (event) => {
      if (event.target.matches("input[type='checkbox']")) return;
      state.selectedId = row.feedback_id;
      renderRows();
      renderDetail();
    });
    tbody.appendChild(tr);
  }
  $("quality-empty").style.display = state.rows.length ? "none" : "block";
  $("quality-count").textContent = `${state.rows.length} records`;
}

function renderDetail() {
  const row = selectedRow();
  $("quality-detail-subtitle").textContent = row ? row.feedback_id : "Select feedback";
  $("quality-save-review").disabled = !row;
  $("quality-dismiss").disabled = !row;
  $("quality-preview").disabled = !row;
  $("quality-export").disabled = !row;
  if (!row) {
    $("quality-detail-list").innerHTML = "";
    $("quality-operator-note").value = "";
    $("quality-promotion-preview").textContent = "";
    return;
  }
  $("quality-review-status").value = row.status;
  $("quality-operator-note").value = row.operator_note || "";
  $("quality-detail-list").innerHTML = `
    <dt>Query</dt><dd>${escapeHtml(row.query)}</dd>
    <dt>Outcome</dt><dd>${escapeHtml(row.outcome)}</dd>
    <dt>Trace</dt><dd>${escapeHtml(row.trace_id || "")}</dd>
    <dt>Search</dt><dd>${escapeHtml(row.search_id || "")}</dd>
    <dt>Build</dt><dd>${escapeHtml(row.build_id || "")}</dd>
    <dt>Note</dt><dd>${escapeHtml(row.note || "")}</dd>
    <dt>Selected</dt><dd><pre>${escapeHtml(JSON.stringify(row.selected_results || [], null, 2))}</pre></dd>
    <dt>Expected</dt><dd><pre>${escapeHtml(JSON.stringify(row.expected || [], null, 2))}</pre></dd>
  `;
}

async function saveReview(status = $("quality-review-status").value) {
  const row = selectedRow();
  if (!row) return;
  const body = await requestJson(`/search/feedback/${encodeURIComponent(row.feedback_id)}`, {
    method: "PATCH",
    body: JSON.stringify({
      kb_name: currentKb(),
      status,
      operator_note: $("quality-operator-note").value,
    }),
  });
  const index = state.rows.findIndex((item) => item.feedback_id === row.feedback_id);
  state.rows[index] = body.feedback;
  renderRows();
  renderDetail();
  setStatus("Review saved.", "success");
}

async function promotion(commit) {
  const ids = selectedIds();
  if (!ids.length) {
    const row = selectedRow();
    if (row) ids.push(row.feedback_id);
  }
  if (!ids.length) return;
  const body = {
    kb_name: currentKb(),
    feedback_ids: ids,
    output_path: $("quality-output-path").value.trim() || null,
    append: $("quality-append").checked,
    overwrite: $("quality-overwrite").checked,
  };
  const path = commit ? "/search/feedback/promote" : "/search/feedback/promote/preview";
  const result = await requestJson(path, { method: "POST", body: JSON.stringify(body) });
  $("quality-promotion-preview").textContent = JSON.stringify(result, null, 2);
  setStatus(commit ? `Exported ${result.cases.length} eval cases.` : `Previewed ${result.cases.length} eval cases.`, "success");
  if (commit) await loadFeedback();
}

function selectedRow() {
  return state.rows.find((row) => row.feedback_id === state.selectedId) || null;
}

function selectedIds() {
  return [...document.querySelectorAll("[data-select-feedback]:checked")].map((node) => node.dataset.selectFeedback);
}

function refSummary(row) {
  const expected = (row.expected || []).length;
  const selected = (row.selected_results || []).length;
  return `${selected} selected / ${expected} expected`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

$("quality-kb-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadFeedback().catch((error) => setStatus(error.message, "error"));
});
$("quality-refresh").addEventListener("click", () => loadFeedback().catch((error) => setStatus(error.message, "error")));
$("quality-save-review").addEventListener("click", () => saveReview().catch((error) => setStatus(error.message, "error")));
$("quality-dismiss").addEventListener("click", () => saveReview("dismissed").catch((error) => setStatus(error.message, "error")));
$("quality-preview").addEventListener("click", () => promotion(false).catch((error) => setStatus(error.message, "error")));
$("quality-preview-selected").addEventListener("click", () => promotion(false).catch((error) => setStatus(error.message, "error")));
$("quality-export").addEventListener("click", () => promotion(true).catch((error) => setStatus(error.message, "error")));

bindSharedApiToken($("quality-api-token"));
loadFeedback().catch((error) => setStatus(error.message, "error"));
