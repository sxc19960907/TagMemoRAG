import { authHeadersFromToken, bindSharedApiToken } from "./admin_token.js";
import { initI18n, t, translatePage } from "./i18n.js";

const config = JSON.parse(document.getElementById("eval-report-config").textContent);

const state = {
  report: null,
  kbName: config.defaultKbName || "default",
};

const $ = (id) => document.getElementById(id);

function tokenHeaders() {
  return authHeadersFromToken($("eval-report-api-token").value);
}

function apiPath(path) {
  return `${config.apiBasePath || ""}${path}`;
}

function setStatus(message, kind = "") {
  const node = $("eval-report-status");
  node.textContent = message ? t(message) : "";
  node.className = `status-strip ${kind}`.trim();
}

function reportPath() {
  return $("eval-report-path").value.trim();
}

function updateLinks() {
  const kb = encodeURIComponent(state.kbName || "default");
  $("eval-report-quality").href = `/admin/retrieval-quality?kb_name=${kb}`;
  $("eval-report-workbench").href = `/admin/rag-workbench?kb_name=${kb}`;
  $("eval-report-qa").href = `/qa?kb_name=${kb}`;
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

async function loadReport() {
  const path = reportPath();
  if (!path) {
    setStatus(t("Enter a report path first."), "error");
    renderEmpty();
    return;
  }
  setStatus(t("Loading eval report..."));
  const body = await requestJson(`/eval/report?path=${encodeURIComponent(path)}`);
  state.report = body;
  state.kbName = (body.kb_names || [])[0] || state.kbName;
  updateLinks();
  renderReport();
  setStatus(t("Eval report loaded."), "success");
}

function renderEmpty() {
  state.report = null;
  $("eval-report-state").className = "status-pill neutral";
  $("eval-report-state").textContent = t("Not loaded");
  $("eval-report-title").textContent = t("Load an eval report");
  $("eval-report-subtitle").textContent = t("Run the suggested eval command, then load its JSON report here.");
  $("eval-report-meta").innerHTML = "";
  renderCounts({});
  $("eval-report-cases").className = "eval-report-case-list empty-state";
  $("eval-report-cases").textContent = t("Load a report to inspect eval cases.");
  $("eval-report-case-count").textContent = `0 ${t("cases")}`;
  $("eval-report-thresholds").textContent = "";
  $("eval-report-config-snapshot").textContent = "";
}

function renderReport() {
  const report = state.report;
  if (!report) {
    renderEmpty();
    return;
  }
  const passed = report.summary?.passed === true;
  $("eval-report-state").className = `status-pill ${passed ? "good" : "needs-review"}`;
  $("eval-report-state").textContent = passed ? t("Passed") : t("Needs review");
  $("eval-report-title").textContent = report.suite || t("Eval report");
  $("eval-report-subtitle").textContent = report.report_path || "";
  $("eval-report-meta").innerHTML = `
    <dt>${t("KB")}</dt><dd>${escapeHtml((report.kb_names || []).join(", ") || "-")}</dd>
    <dt>${t("Docs")}</dt><dd>${escapeHtml(report.docs || "-")}</dd>
    <dt>${t("Top K")}</dt><dd>${escapeHtml(report.top_k || "-")}</dd>
    <dt>${t("Status")}</dt><dd>${escapeHtml(passed ? t("Passed") : t("Needs review"))}</dd>
  `;
  renderCounts(report);
  renderCases();
  $("eval-report-thresholds").textContent = JSON.stringify(report.thresholds || {}, null, 2);
  $("eval-report-config-snapshot").textContent = JSON.stringify(report.config_snapshot || {}, null, 2);
}

function renderCounts(report) {
  const counts = report.counts || {};
  const metrics = report.summary || {};
  $("eval-report-count-total").textContent = String(counts.total || metrics.cases || 0);
  $("eval-report-count-failed").textContent = String(counts.failed || 0);
  $("eval-report-metric-recall").textContent = metric(metrics.recall_at_k);
  $("eval-report-metric-mrr").textContent = metric(metrics.mrr);
  $("eval-report-metric-hit").textContent = metric(metrics.hit_at_k);
}

function renderCases() {
  const report = state.report || {};
  const filter = $("eval-report-filter").value;
  const cases = (report.cases || []).filter((item) => {
    if (filter === "failed") return item.passed === false;
    if (filter === "passed") return item.passed === true;
    if (filter === "needs-review") return item.status !== "ok";
    return true;
  });
  $("eval-report-case-count").textContent = `${cases.length} ${t("cases")}`;
  const node = $("eval-report-cases");
  if (!cases.length) {
    node.className = "eval-report-case-list empty-state";
    node.textContent = t("No cases match this filter.");
    return;
  }
  node.className = "eval-report-case-list";
  node.innerHTML = cases.map(renderCaseCard).join("");
}

function renderCaseCard(item) {
  const statusClass = item.status === "ok" ? "good" : item.status === "urgent" ? "needs-review" : "in-progress";
  const failures = (item.failures || []).map((failure) => `<li>${escapeHtml(failure)}</li>`).join("");
  const guidance = (item.guidance || []).map(renderGuidanceItem).join("");
  const expected = (item.expected || []).map(renderExpected).join("");
  const actual = (item.actual_top_k || []).map(renderActualResult).join("");
  return `
    <article class="eval-report-case-card ${escapeHtml(item.status || "")}">
      <header>
        <div>
          <span class="status-pill ${statusClass}">${escapeHtml(statusLabel(item.status))}</span>
          <h3>${escapeHtml(item.id || t("Eval case"))}</h3>
          <p>${escapeHtml(item.query || "")}</p>
        </div>
        <dl>
          <dt>${t("Recall")}</dt><dd>${metric(item.metrics?.recall_at_k)}</dd>
          <dt>${t("MRR")}</dt><dd>${metric(item.metrics?.mrr)}</dd>
          <dt>${t("Hit")}</dt><dd>${metric(item.metrics?.hit_at_k)}</dd>
        </dl>
      </header>
      ${guidance ? `<section class="eval-report-guidance"><strong>${t("Recommended Fix")}</strong>${guidance}</section>` : ""}
      ${failures ? `<section class="eval-report-failures"><strong>${t("Failures")}</strong><ul>${failures}</ul></section>` : ""}
      <div class="eval-report-evidence-grid">
        <section>
          <h4>${t("Expected Evidence")}</h4>
          ${expected || `<p class="muted">${t("No expected evidence.")}</p>`}
        </section>
        <section>
          <h4>${t("Actual Top Results")}</h4>
          ${actual || `<p class="muted">${t("No actual results.")}</p>`}
        </section>
      </div>
    </article>
  `;
}

function renderGuidanceItem(item) {
  const severityClass = item.severity === "urgent" ? "needs-review" : "in-progress";
  return `
    <article class="eval-report-guidance-card ${escapeHtml(item.code || "")}">
      <span class="status-pill ${severityClass}">${escapeHtml(t(item.severity === "urgent" ? "Urgent" : "Review"))}</span>
      <div>
        <h4>${escapeHtml(t(item.title || "Review failed case"))}</h4>
        <p>${escapeHtml(t(item.explanation || ""))}</p>
        <small>${escapeHtml(t(item.next_action || ""))}</small>
      </div>
    </article>
  `;
}

function renderExpected(item) {
  return `
    <div class="eval-report-mini-card">
      <strong>${escapeHtml(item.source_file || item.header || item.id || t("Expected"))}</strong>
      ${item.header ? `<small>${t("Section")}: ${escapeHtml(item.header)}</small>` : ""}
      ${Array.isArray(item.text_contains) && item.text_contains.length ? `<small>${t("Must contain")}: ${escapeHtml(item.text_contains.join(", "))}</small>` : ""}
      ${item.metadata && Object.keys(item.metadata).length ? `<small>${t("Metadata")}: ${escapeHtml(JSON.stringify(item.metadata))}</small>` : ""}
    </div>
  `;
}

function renderActualResult(item, index) {
  const matches = Array.isArray(item.matched_expected_indexes) && item.matched_expected_indexes.length
    ? ` · ${t("Matched")} ${item.matched_expected_indexes.join(", ")}`
    : "";
  const title = item.source_file || item.header || item.path || `${t("Result")} ${index + 1}`;
  return `
    <div class="eval-report-mini-card">
      <strong>${escapeHtml(title)}</strong>
      <small>${t("Rank")} ${escapeHtml(item.rank || index + 1)}${matches}</small>
      ${item.header ? `<small>${t("Section")}: ${escapeHtml(item.header)}</small>` : ""}
      ${item.score !== undefined ? `<small>${t("Score")}: ${escapeHtml(Number(item.score).toFixed(4))}</small>` : ""}
      ${item.text ? `<p>${escapeHtml(item.text)}</p>` : ""}
    </div>
  `;
}

function statusLabel(status) {
  if (status === "urgent") return t("Urgent");
  if (status === "review") return t("Review");
  return t("OK");
}

function metric(value) {
  return Number(value || 0).toFixed(3);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

$("eval-report-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadReport().catch((error) => {
    renderEmpty();
    setStatus(error.message, "error");
  });
});

$("eval-report-filter").addEventListener("change", renderCases);

bindSharedApiToken($("eval-report-api-token"));
initI18n({ mount: ".top-actions" });
updateLinks();
renderEmpty();
if (reportPath()) {
  loadReport().catch((error) => setStatus(error.message, "error"));
}
translatePage();
