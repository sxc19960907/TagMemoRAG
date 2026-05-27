import { authHeadersFromToken, bindSharedApiToken } from "./admin_token.js";
import { initI18n, t, translatePage } from "./i18n.js";

const config = JSON.parse(document.getElementById("retrieval-quality-config").textContent);
const initialParams = new URLSearchParams(window.location.search);
const initialFeedbackId = initialParams.get("feedback_id") || "";

const state = {
  rows: [],
  selectedId: initialFeedbackId || null,
  requestedFeedbackId: initialFeedbackId,
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
  node.textContent = message ? t(message) : "";
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

function updateLinks() {
  const kb = encodeURIComponent(currentKb());
  $("quality-workbench").href = `/admin/rag-workbench?kb_name=${kb}`;
  $("quality-readiness").href = `/admin/rag-readiness?kb_name=${kb}`;
  $("quality-manual-library").href = `/admin/manual-library?kb_name=${kb}`;
  $("quality-people").href = `/admin/people?kb_name=${kb}`;
  $("quality-qa").href = `/qa?kb_name=${kb}`;
}

async function loadFeedback() {
  updateLinks();
  const params = new URLSearchParams({ kb_name: currentKb(), limit: $("quality-filter-limit").value || "50" });
  for (const [key, id] of [
    ["status", "quality-filter-status"],
    ["outcome", "quality-filter-outcome"],
    ["query", "quality-filter-query"],
  ]) {
    const value = $(id).value.trim();
    if (value) params.set(key, value);
  }
  setStatus(t("Loading feedback..."));
  const body = await requestJson(`/search/feedback?${params.toString()}`, { method: "GET" });
  state.rows = body.feedback || [];
  selectFeedbackFromUrl();
  state.selectedId = state.rows.some((row) => row.feedback_id === state.selectedId) ? state.selectedId : null;
  renderSummary();
  renderRows();
  renderDetail();
  setStatus(`Loaded ${state.rows.length} feedback records.`, "success");
}

function selectFeedbackFromUrl() {
  if (!state.requestedFeedbackId) return;
  if (state.rows.some((row) => row.feedback_id === state.requestedFeedbackId)) {
    state.selectedId = state.requestedFeedbackId;
    state.requestedFeedbackId = "";
  }
}

function renderSummary() {
  const rows = state.rows || [];
  $("quality-summary-needs-review").textContent = String(rows.filter((row) => row.status === "new" && row.outcome !== "helpful").length);
  $("quality-summary-helpful").textContent = String(rows.filter((row) => row.outcome === "helpful").length);
  $("quality-summary-not-helpful").textContent = String(rows.filter((row) => row.outcome === "not_helpful").length);
  $("quality-summary-promotable").textContent = String(rows.filter(isPromotionReady).length);
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
      <td><span class="quality-source-pill ${escapeHtml(sourceKind(row))}">${escapeHtml(sourceLabel(row))}</span></td>
      <td>${escapeHtml((row.created_at || "").slice(0, 19))}</td>
      <td><span class="status-pill ${escapeHtml(outcomeClass(row.outcome))}">${escapeHtml(outcomeLabel(row.outcome))}</span></td>
      <td><span class="status-pill ${escapeHtml(statusClass(row.status))}">${escapeHtml(row.status)}</span></td>
      <td class="query-cell">${escapeHtml(row.query)}</td>
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
  $("quality-count").textContent = `${state.rows.length} ${t("records")}`;
}

function renderDetail() {
  const row = selectedRow();
  $("quality-detail-subtitle").textContent = row ? row.feedback_id : t("Select feedback");
  $("quality-save-review").disabled = !row;
  $("quality-dismiss").disabled = !row;
  $("quality-preview").disabled = !row;
  $("quality-export").disabled = !row;
  $("quality-triage-use-selected").disabled = !row;
  $("quality-mark-triaged").disabled = !row;
  $("quality-triage-preview").disabled = !row;
  if (!row) {
    $("quality-detail-list").innerHTML = "";
    $("quality-review-guidance").hidden = true;
    $("quality-review-guidance").textContent = "";
    renderTriageDecision(null);
    $("quality-selected-evidence").className = "quality-ref-list empty-state";
    $("quality-selected-evidence").textContent = t("Select feedback to inspect cited sources.");
    $("quality-expected-evidence").className = "quality-ref-list empty-state";
    $("quality-expected-evidence").textContent = t("Add expected references before promoting difficult cases.");
    setExpectedEditor(null);
    $("quality-operator-note").value = "";
    $("quality-promotion-summary").className = "quality-promotion-summary empty-state";
    $("quality-promotion-summary").textContent = t("Preview promotion to see export readiness.");
    $("quality-promotion-preview").textContent = "";
    return;
  }
  $("quality-review-status").value = row.status;
  $("quality-operator-note").value = row.operator_note || "";
  renderGuidance(row);
  renderTriageDecision(row);
  $("quality-detail-list").innerHTML = `
    <dt>${t("Query")}</dt><dd>${escapeHtml(row.query)}</dd>
    <dt>${t("Source")}</dt><dd><span class="quality-source-pill ${escapeHtml(sourceKind(row))}">${escapeHtml(sourceLabel(row))}</span></dd>
    <dt>${t("Outcome")}</dt><dd>${escapeHtml(outcomeLabel(row.outcome))}</dd>
    <dt>${t("Status")}</dt><dd>${escapeHtml(row.status || "")}</dd>
    <dt>${t("Trace")}</dt><dd>${escapeHtml(row.trace_id || "")}</dd>
    <dt>${t("Search")}</dt><dd>${escapeHtml(row.search_id || "")}</dd>
    <dt>${t("Retrieve")}</dt><dd>${escapeHtml(row.retrieve_id || "")}</dd>
    <dt>${t("Plan")}</dt><dd>${escapeHtml(row.plan_id || "")}</dd>
    <dt>${t("Build")}</dt><dd>${escapeHtml(row.build_id || "")}</dd>
    <dt>${t("Answerable")}</dt><dd>${escapeHtml(answerableLabel(row.answerable))}</dd>
    <dt>${t("Failure")}</dt><dd>${escapeHtml(row.failure_reason || "")}</dd>
    <dt>${t("Note")}</dt><dd>${escapeHtml(row.note || "")}</dd>
  `;
  renderRefList("quality-selected-evidence", selectedRefCards(row), t("No selected retrieval references were captured."));
  renderRefList("quality-expected-evidence", expectedRefCards(row), t("No expected references yet. Add them before promoting this as a regression case."));
  setExpectedEditor(row.expected?.[0] || null);
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
      expected: expectedFromEditor(),
    }),
  });
  const index = state.rows.findIndex((item) => item.feedback_id === row.feedback_id);
  state.rows[index] = body.feedback;
  renderSummary();
  renderRows();
  renderDetail();
  setStatus(t("Review saved."), "success");
}

function setExpectedEditor(ref) {
  $("quality-expected-source").value = ref?.source_file || "";
  $("quality-expected-header").value = ref?.header || "";
  $("quality-expected-text").value = Array.isArray(ref?.text_contains) ? ref.text_contains.join(", ") : "";
  $("quality-expected-manual").value = ref?.metadata?.manual_id || "";
}

function expectedFromEditor() {
  const sourceFile = $("quality-expected-source").value.trim();
  const header = $("quality-expected-header").value.trim();
  const textContains = $("quality-expected-text").value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const manualId = $("quality-expected-manual").value.trim();
  if (!sourceFile && !header && textContains.length === 0 && !manualId) return [];
  return [{
    source_file: sourceFile,
    header,
    text_contains: textContains,
    metadata: manualId ? { manual_id: manualId } : {},
  }];
}

function useSelectedAsExpected() {
  const row = selectedRow();
  if (!row) return;
  const first = (row.selected_results || [])[0];
  if (!first) return;
  setExpectedEditor({
    source_file: first.source_file || "",
    header: first.header || "",
    text_contains: [],
    metadata: first.manual_id ? { manual_id: first.manual_id } : {},
  });
}

function renderTriageDecision(row) {
  const panel = $("quality-triage-panel");
  if (!row) {
    panel.className = "quality-triage-panel empty-state";
    panel.textContent = t("Select feedback to see the recommended review route.");
    $("quality-triage-use-selected").disabled = true;
    $("quality-mark-triaged").disabled = true;
    $("quality-triage-preview").disabled = true;
    return;
  }
  const decision = triageDecision(row);
  panel.className = `quality-triage-panel ${decision.tone}`;
  panel.innerHTML = `
    <span class="quality-triage-badge">${escapeHtml(t(decision.badge))}</span>
    <strong>${escapeHtml(t(decision.title))}</strong>
    <p>${escapeHtml(t(decision.body))}</p>
  `;
  const selectedCount = (row.selected_results || []).length;
  $("quality-triage-use-selected").disabled = selectedCount === 0 || row.status === "dismissed";
  $("quality-mark-triaged").disabled = row.status === "triaged" || row.status === "promoted" || row.status === "dismissed";
  $("quality-triage-preview").disabled = row.status === "dismissed";
}

function triageDecision(row) {
  const expectedCount = (row.expected || []).length;
  const selectedCount = (row.selected_results || []).length;
  if (row.status === "dismissed") {
    return {
      tone: "muted",
      badge: "Excluded",
      title: "Dismissed case",
      body: "This feedback is dismissed and excluded from promotion exports.",
    };
  }
  if (row.status === "promoted") {
    return {
      tone: "ready",
      badge: "Promoted",
      title: "Already promoted",
      body: "This feedback has already been exported as an eval case.",
    };
  }
  if (expectedCount > 0) {
    return {
      tone: "ready",
      badge: "Ready",
      title: "Ready to preview or export",
      body: "Expected evidence is present. Preview the eval draft, then export if the matcher looks stable.",
    };
  }
  if (row.outcome === "helpful" && selectedCount > 0) {
    return {
      tone: "ready",
      badge: "Positive candidate",
      title: "Useful answer to preserve",
      body: "This helpful answer can be previewed as a positive regression case.",
    };
  }
  if (selectedCount > 0) {
    return {
      tone: "attention",
      badge: "Needs expected evidence",
      title: "Confirm the correct source",
      body: "Use selected evidence if it is correct, or enter the source that should have answered this question before promotion.",
    };
  }
  if (row.outcome === "missing_result" || row.outcome === "wrong_manual" || row.outcome === "not_helpful") {
    return {
      tone: "attention",
      badge: "Needs expected evidence",
      title: "Capture the missing answer source",
      body: "Add source, section, text, or manual metadata before this feedback can become a stable eval case.",
    };
  }
  return {
    tone: "neutral",
    badge: "Review",
    title: "Review and classify",
    body: "Read the feedback, add an operator note, then mark it triaged or dismiss it.",
  };
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
  renderPromotionSummary(result);
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

function sourceKind(row) {
  const note = String(row.note || "").toLowerCase();
  if (note.startsWith("q&a feedback")) return "qa";
  if (row.retrieve_id) return "retrieve";
  return "search";
}

function sourceLabel(row) {
  const kind = sourceKind(row);
  if (kind === "qa") return "Q&A";
  if (kind === "retrieve") return "Retrieve";
  return "Search";
}

function outcomeLabel(outcome) {
  if (outcome === "not_helpful") return "Not helpful";
  if (outcome === "missing_result") return "Missing result";
  if (outcome === "wrong_manual") return "Wrong manual";
  if (outcome === "helpful") return "Helpful";
  return outcome || "";
}

function outcomeClass(outcome) {
  if (outcome === "helpful") return "good";
  if (outcome === "not_helpful" || outcome === "missing_result" || outcome === "wrong_manual") return "needs-review";
  return "neutral";
}

function statusClass(status) {
  if (status === "promoted") return "good";
  if (status === "dismissed") return "neutral";
  if (status === "triaged") return "in-progress";
  return "needs-review";
}

function answerableLabel(value) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "";
}

function isPromotionReady(row) {
  return row.status !== "dismissed" && ((row.expected || []).length > 0 || (row.outcome === "helpful" && (row.selected_results || []).length > 0));
}

function renderGuidance(row) {
  const guidance = $("quality-review-guidance");
  const text = reviewGuidance(row);
  guidance.hidden = !text;
  guidance.textContent = text;
}

function reviewGuidance(row) {
  if (row.outcome === "helpful" && (row.selected_results || []).length > 0) {
    return t("This helpful answer can be promoted as a positive regression sample.");
  }
  if (row.outcome === "not_helpful") {
    return t("Review the cited evidence, then add expected evidence before promoting this negative case.");
  }
  if (row.outcome === "missing_result") {
    return t("Capture the source that should have matched before exporting this case.");
  }
  if (row.outcome === "wrong_manual") {
    return t("Check the selected manual and record the correct manual or section.");
  }
  return "";
}

function selectedRefCards(row) {
  const evidenceIds = Array.isArray(row.selected_evidence_ids) ? row.selected_evidence_ids : [];
  const contextIds = Array.isArray(row.selected_context_item_ids) ? row.selected_context_item_ids : [];
  return (row.selected_results || []).map((ref, index) => ({
    title: ref.source_file || ref.manual_id || `Selected ${index + 1}`,
    meta: [
      ref.header ? `Section: ${ref.header}` : "",
      ref.rank ? `Rank: ${ref.rank}` : "",
      ref.node_id !== null && ref.node_id !== undefined ? `Node: ${ref.node_id}` : "",
      ref.manual_id ? `Manual: ${ref.manual_id}` : "",
      ref.anchor_key ? `Anchor: ${ref.anchor_key}` : "",
    ].filter(Boolean),
    badges: [
      evidenceIds[index] ? `Evidence ${evidenceIds[index]}` : "",
      contextIds[index] ? `Context ${contextIds[index]}` : "",
    ].filter(Boolean),
  }));
}

function expectedRefCards(row) {
  return (row.expected || []).map((ref, index) => ({
    title: ref.source_file || ref.header || `Expected ${index + 1}`,
    meta: [
      ref.header ? `Section: ${ref.header}` : "",
      ref.anchor_key ? `Anchor: ${ref.anchor_key}` : "",
      Array.isArray(ref.text_contains) && ref.text_contains.length ? `Must contain: ${ref.text_contains.join(", ")}` : "",
      ref.metadata && Object.keys(ref.metadata).length ? `Metadata: ${JSON.stringify(ref.metadata)}` : "",
    ].filter(Boolean),
    badges: ["Expected"],
  }));
}

function renderRefList(id, cards, emptyText) {
  const node = $(id);
  if (!cards.length) {
    node.className = "quality-ref-list empty-state";
    node.textContent = emptyText;
    return;
  }
  node.className = "quality-ref-list";
  node.innerHTML = cards.map((card) => `
    <article class="quality-ref-card">
      <div>
        <strong>${escapeHtml(card.title)}</strong>
        ${card.meta.map((item) => `<small>${escapeHtml(item)}</small>`).join("")}
      </div>
      ${card.badges.length ? `<p>${card.badges.map((badge) => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}</p>` : ""}
    </article>
  `).join("");
}

function renderPromotionSummary(result) {
  const cases = Array.isArray(result?.cases) ? result.cases : [];
  const skipped = Array.isArray(result?.skipped) ? result.skipped : [];
  const summary = result?.summary || {};
  const node = $("quality-promotion-summary");
  if (!cases.length && !skipped.length) {
    node.className = "quality-promotion-summary empty-state";
    node.textContent = t("No promotion preview results.");
    return;
  }
  node.className = "quality-promotion-summary";
  const summaryCard = `
    <article class="quality-promotion-card summary">
      <span>${t("Eval draft")}</span>
      <strong>${escapeHtml(summary.suite_path || summary.output_path || result?.output_path || "")}</strong>
      ${summary.report_path ? `<small>${t("Report")}: ${escapeHtml(summary.report_path)}</small>` : ""}
      <small>${escapeHtml(summary.ready_count ?? cases.length)} ${t("ready")} / ${escapeHtml(summary.skipped_count ?? skipped.length)} ${t("skipped")}</small>
      ${summary.next_command ? `<code>${escapeHtml(summary.next_command)}</code>` : ""}
      ${summary.command_note ? `<small>${escapeHtml(summary.command_note)}</small>` : ""}
      ${summary.report_path ? `<a class="button-link compact" href="${escapeHtml(reportViewerHref(summary.report_path))}">${t("Open report")}</a>` : ""}
      ${summary.suite_path ? `<a class="button-link compact" href="${escapeHtml(evalLauncherHref(summary.suite_path))}">${t("Run in browser")}</a>` : ""}
    </article>
  `;
  const caseCards = cases.map((item) => `
    <article class="quality-promotion-card ready ${escapeHtml(promotionQualityClass(item.quality))}">
      <span>${escapeHtml(t(promotionQualityLabel(item.quality)))}</span>
      <strong>${escapeHtml(item.id || t("Eval case"))}</strong>
      <small>${escapeHtml(item.query || "")}</small>
      <small>${escapeHtml((item.relevant || []).length)} ${t("matcher(s)")}</small>
      ${promotionQualityText(item.quality) ? `<small>${escapeHtml(t(promotionQualityText(item.quality)))}</small>` : ""}
    </article>
  `);
  const skippedCards = skipped.map((item) => `
    <article class="quality-promotion-card blocked">
      <span>${t("Needs input")}</span>
      <strong>${escapeHtml(item.feedback_id || t("Feedback"))}</strong>
      <small>${escapeHtml(item.message || skipReasonLabel(item.reason))}</small>
      <small>${escapeHtml(item.next_action || "")}</small>
    </article>
  `);
  node.innerHTML = [summaryCard, ...caseCards, ...skippedCards].join("");
}

function promotionQualityClass(quality) {
  return quality?.level === "weak" ? "weak" : "strong";
}

function promotionQualityLabel(quality) {
  return quality?.level === "weak" ? "Weak matcher" : "Ready";
}

function promotionQualityText(quality) {
  if (!quality) return "";
  return quality.message || "";
}

function skipReasonLabel(reason) {
  if (reason === "query_too_short") return t("Feedback query is too short to become a stable eval case.");
  if (reason === "no_usable_relevant_matcher") return t("No usable relevant matcher is available for this feedback.");
  if (reason === "duplicate_case_id") return t("An eval case with this feedback id already exists at the output path.");
  return String(reason || "");
}

function reportViewerHref(reportPath) {
  const params = new URLSearchParams({ kb_name: currentKb(), report_path: reportPath });
  return `/admin/eval-report?${params.toString()}`;
}

function evalLauncherHref(suitePath) {
  const params = new URLSearchParams({ kb_name: currentKb(), suite_path: suitePath });
  return `/admin/eval-report?${params.toString()}`;
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
  updateLinks();
  loadFeedback().catch((error) => setStatus(error.message, "error"));
});
$("quality-refresh").addEventListener("click", () => loadFeedback().catch((error) => setStatus(error.message, "error")));
$("quality-save-review").addEventListener("click", () => saveReview().catch((error) => setStatus(error.message, "error")));
$("quality-dismiss").addEventListener("click", () => saveReview("dismissed").catch((error) => setStatus(error.message, "error")));
$("quality-preview").addEventListener("click", () => promotion(false).catch((error) => setStatus(error.message, "error")));
$("quality-preview-selected").addEventListener("click", () => promotion(false).catch((error) => setStatus(error.message, "error")));
$("quality-export").addEventListener("click", () => promotion(true).catch((error) => setStatus(error.message, "error")));
$("quality-use-selected-expected").addEventListener("click", useSelectedAsExpected);
$("quality-triage-use-selected").addEventListener("click", useSelectedAsExpected);
$("quality-mark-triaged").addEventListener("click", () => saveReview("triaged").catch((error) => setStatus(error.message, "error")));
$("quality-triage-preview").addEventListener("click", () => promotion(false).catch((error) => setStatus(error.message, "error")));
$("quality-clear-expected").addEventListener("click", () => setExpectedEditor(null));

bindSharedApiToken($("quality-api-token"));
initI18n({ mount: ".top-actions" });
updateLinks();
loadFeedback().catch((error) => setStatus(error.message, "error"));
translatePage();
