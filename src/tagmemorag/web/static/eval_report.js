import { authHeadersFromToken, bindSharedApiToken } from "./admin_token.js";
import { initI18n, t, translatePage } from "./i18n.js";

const config = JSON.parse(document.getElementById("eval-report-config").textContent);

const state = {
  report: null,
  recentReports: [],
  suites: [],
  activeRun: null,
  runPollTimer: null,
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

async function postJson(path, payload) {
  const response = await fetch(apiPath(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...tokenHeaders(),
    },
    body: JSON.stringify(payload),
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

async function loadEvalSuites() {
  const body = await requestJson("/eval/suites");
  state.suites = Array.isArray(body.suites) ? body.suites : [];
  renderEvalSuites();
}

function renderEvalSuites() {
  const select = $("eval-run-suite");
  if (!state.suites.length) {
    select.innerHTML = `<option value="">${t("No eval suites available")}</option>`;
    $("eval-run-start").disabled = true;
    $("eval-run-status").className = "eval-run-status empty-state";
    $("eval-run-status").textContent = t("No eval suites available.");
    renderSuiteHistory();
    return;
  }
  select.innerHTML = state.suites.map((suite) => `
    <option value="${escapeHtml(suite.suite_id)}">${escapeHtml(suiteOptionLabel(suite))}</option>
  `).join("");
  const preferred = state.suites.find((suite) => suite.suite_path === config.defaultSuitePath);
  if (preferred) {
    select.value = preferred.suite_id;
  }
  $("eval-run-start").disabled = false;
  renderRunIdle();
  renderSuiteHistory();
}

async function startEvalRun() {
  const suiteId = $("eval-run-suite").value;
  if (!suiteId) {
    setStatus(t("Select an eval suite first."), "error");
    return;
  }
  $("eval-run-start").disabled = true;
  renderRunMessage(t("Starting eval run..."));
  const job = await postJson("/eval/runs", { suite_id: suiteId });
  state.activeRun = job;
  renderEvalRun(job);
  pollEvalRun(job.job_id);
}

function selectSuite(suiteId) {
  if (!suiteId) return;
  $("eval-run-suite").value = suiteId;
  renderRunIdle();
  renderSuiteHistory();
}

async function runSuite(suiteId) {
  selectSuite(suiteId);
  await startEvalRun();
}

async function pollEvalRun(jobId) {
  clearRunPoll();
  const tick = async () => {
    const job = await requestJson(`/eval/runs/${encodeURIComponent(jobId)}`);
    state.activeRun = job;
    renderEvalRun(job);
    if (["queued", "running"].includes(job.status)) {
      state.runPollTimer = window.setTimeout(tick, 900);
      return;
    }
    $("eval-run-start").disabled = false;
    if (job.report_path) {
      await loadEvalSuites().catch(() => {});
      await loadRecentReports().catch(() => {});
    }
  };
  state.runPollTimer = window.setTimeout(tick, 250);
}

function renderRunIdle() {
  const suite = selectedSuite();
  $("eval-run-status").className = "eval-run-status";
  $("eval-run-status").innerHTML = suite
    ? `
      <strong>${escapeHtml(t(suite.name))}</strong>
      <p>${escapeHtml(t(suite.description || ""))}</p>
      <small>${escapeHtml(suiteMetaText(suite))}</small>
      <small>${escapeHtml(suite.suite_path || "")}</small>
    `
    : t("Select an eval suite first.");
}

function renderSuiteHistory() {
  const node = $("eval-suite-history");
  const suites = state.suites || [];
  $("eval-suite-history-count").textContent = suites.length
    ? `${suites.length} ${t("suites")}`
    : t("No eval suites available.");
  if (!suites.length) {
    node.className = "eval-suite-history empty-state";
    node.textContent = t("No eval suites available.");
    return;
  }
  node.className = "eval-suite-history";
  node.innerHTML = suites.map(renderSuiteHistoryCard).join("");
}

function renderSuiteHistoryCard(suite) {
  const selected = selectedSuite()?.suite_id === suite.suite_id;
  const latest = suite.latest_report || null;
  const latestClass = latest
    ? latest.passed === true
      ? "good"
      : latest.passed === false
        ? "needs-review"
        : "neutral"
    : "neutral";
  const latestLabel = latest
    ? latest.passed === true
      ? t("Latest passed")
      : latest.passed === false
        ? t("Latest needs review")
        : t("Latest ready")
    : t("Not run yet");
  const latestMeta = latest
    ? `${Number(latest.cases || 0)} ${t("cases")} · ${Number(latest.failed || 0)} ${t("failed")} · ${formatModified(latest.modified_at)}`
    : t("Run this suite to create a browser report.");
  const latestActions = latest?.path
    ? `
      <a class="button-link compact" href="/admin/eval-report?report_path=${encodeURIComponent(latest.path)}">${t("Open latest")}</a>
      <button class="button-link compact" type="button" data-load-suite-report="${escapeHtml(suite.suite_id)}">${t("Load latest")}</button>
    `
    : "";
  return `
    <article class="eval-suite-card ${selected ? "selected" : ""}">
      <header>
        <div>
          <span class="status-pill ${latestClass}">${escapeHtml(latestLabel)}</span>
          <h3>${escapeHtml(t(suite.name || suite.suite_id))}</h3>
          <p>${escapeHtml(t(suite.description || ""))}</p>
        </div>
        <button class="button-link compact" type="button" data-select-suite="${escapeHtml(suite.suite_id)}">${selected ? t("Selected") : t("Select")}</button>
      </header>
      <dl class="eval-suite-meta">
        <dt>${t("Type")}</dt><dd>${escapeHtml(t(suite.kind === "feedback_draft" ? "Feedback draft" : "Fixture suite"))}</dd>
        <dt>${t("Cases")}</dt><dd>${Number(suite.case_count || 0) || "-"}</dd>
        <dt>${t("Mode")}</dt><dd>${escapeHtml(t(suite.reuse_built_kb ? "Uses current KB" : "Builds from docs"))}</dd>
        <dt>${t("Updated")}</dt><dd>${escapeHtml(suite.modified_at ? formatModified(suite.modified_at) : "-")}</dd>
      </dl>
      <div class="eval-suite-latest">
        <strong>${t("Latest report")}</strong>
        <small>${escapeHtml(latestMeta)}</small>
        ${latest?.relative_path ? `<small>${escapeHtml(latest.relative_path)}</small>` : ""}
      </div>
      <div class="eval-run-actions">
        <button class="primary compact" type="button" data-run-suite="${escapeHtml(suite.suite_id)}">${t("Run eval")}</button>
        ${latestActions}
      </div>
    </article>
  `;
}

function renderRunMessage(message) {
  $("eval-run-status").className = "eval-run-status empty-state";
  $("eval-run-status").textContent = message;
}

function renderEvalRun(job) {
  const terminal = !["queued", "running"].includes(job.status);
  const statusClass = job.status === "passed" ? "good" : terminal ? "needs-review" : "in-progress";
  const summary = job.summary || {};
  const reportLink = job.report_path
    ? `<a class="button-link compact" href="${escapeHtml(job.report_url || `/admin/eval-report?report_path=${encodeURIComponent(job.report_path)}`)}">${t("Open Report")}</a>
       <button class="button-link compact" type="button" id="eval-run-load-report">${t("Load here")}</button>`
    : "";
  const error = job.error ? `<p>${escapeHtml(job.error.message || job.error.type || "")}</p>` : "";
  $("eval-run-status").className = "eval-run-status";
  $("eval-run-status").innerHTML = `
    <span class="status-pill ${statusClass}">${escapeHtml(t(runStatusLabel(job.status)))}</span>
    <strong>${escapeHtml(t(job.suite?.name || "Eval run"))}</strong>
    <p>${escapeHtml(runSummaryText(job, summary))}</p>
    ${error}
    <div class="eval-run-actions">${reportLink}</div>
  `;
  const loadButton = $("eval-run-load-report");
  if (loadButton) {
    loadButton.addEventListener("click", () => {
      $("eval-report-path").value = job.report_path;
      loadReport().catch((err) => setStatus(err.message, "error"));
    });
  }
}

function selectedSuite() {
  const suiteId = $("eval-run-suite").value;
  return state.suites.find((suite) => suite.suite_id === suiteId);
}

function suiteOptionLabel(suite) {
  const count = Number(suite.case_count || 0);
  const suffix = count ? ` · ${count} ${t("cases")}` : "";
  return `${t(suite.name || suite.suite_id)}${suffix}`;
}

function suiteMetaText(suite) {
  const parts = [];
  parts.push(t(suite.kind === "feedback_draft" ? "Feedback draft" : "Fixture suite"));
  if (suite.reuse_built_kb) {
    parts.push(t("Uses current KB"));
  } else if (suite.docs_path) {
    parts.push(t("Builds from docs"));
  }
  if (suite.case_count) {
    parts.push(`${Number(suite.case_count)} ${t("cases")}`);
  }
  if (suite.modified_at) {
    parts.push(`${t("Updated")} ${formatModified(suite.modified_at)}`);
  }
  return parts.join(" · ");
}

function runStatusLabel(status) {
  if (status === "queued") return "Queued";
  if (status === "running") return "Running";
  if (status === "passed") return "Passed";
  if (status === "failed") return "Needs review";
  return "Error";
}

function runSummaryText(job, summary) {
  if (job.status === "queued") return t("Eval run is queued.");
  if (job.status === "running") return t("Eval run is running.");
  if (job.status === "passed" || job.status === "failed") {
    return `${Number(summary.cases || 0)} ${t("cases")} · ${t("Recall")} ${metric(summary.recall_at_k)} · ${t("MRR")} ${metric(summary.mrr)} · ${t("Hit")} ${metric(summary.hit_at_k)}`;
  }
  return t("Eval run failed.");
}

function clearRunPoll() {
  if (state.runPollTimer) {
    window.clearTimeout(state.runPollTimer);
    state.runPollTimer = null;
  }
}

async function loadRecentReports() {
  $("eval-report-recents-count").textContent = t("Looking for recent eval reports...");
  const body = await requestJson("/eval/reports?limit=20");
  state.recentReports = Array.isArray(body.reports) ? body.reports : [];
  renderRecentReports();
}

function renderRecentReports() {
  const node = $("eval-report-recents");
  const reports = state.recentReports || [];
  $("eval-report-recents-count").textContent = `${reports.length} ${t("reports")}`;
  if (!reports.length) {
    node.className = "eval-report-recents empty-state";
    node.textContent = t("No recent eval reports found.");
    return;
  }
  node.className = "eval-report-recents";
  node.innerHTML = reports.map(renderRecentReport).join("");
}

function renderRecentReport(item, index) {
  const status = item.valid
    ? item.passed === true
      ? t("Passed")
      : item.passed === false
        ? t("Needs review")
        : t("Ready")
    : t("Unreadable");
  const statusClass = item.valid
    ? item.passed === true
      ? "good"
      : item.passed === false
        ? "needs-review"
        : "neutral"
    : "needs-review";
  const title = item.suite || item.relative_path || item.name || t("Eval report");
  const meta = item.valid
    ? `${Number(item.cases || 0)} ${t("cases")} · ${Number(item.failed || 0)} ${t("failed")}`
    : t(item.error || "Unable to read report");
  return `
    <button class="eval-report-recent-card" type="button" data-report-index="${index}">
      <span class="status-pill ${statusClass}">${escapeHtml(status)}</span>
      <strong>${escapeHtml(title)}</strong>
      <small>${escapeHtml(meta)}</small>
      <small>${escapeHtml(formatModified(item.modified_at))} · ${escapeHtml(item.relative_path || item.path || "")}</small>
    </button>
  `;
}

function loadRecentReport(index) {
  const item = state.recentReports[index];
  if (!item?.path) return;
  $("eval-report-path").value = item.path;
  loadReport().catch((error) => {
    renderEmpty();
    setStatus(error.message, "error");
  });
}

function loadSuiteLatestReport(suiteId) {
  const suite = state.suites.find((item) => item.suite_id === suiteId);
  const path = suite?.latest_report?.path;
  if (!path) return;
  $("eval-report-path").value = path;
  loadReport().catch((error) => {
    renderEmpty();
    setStatus(error.message, "error");
  });
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
          <p class="eval-report-case-actions">
            <a class="button-link compact" href="${escapeHtml(caseQaHref(item))}">${t("Ask in Q&A")}</a>
            <a class="button-link compact" href="${escapeHtml(caseWorkbenchHref(item))}">${t("Open in Workbench")}</a>
          </p>
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

function caseQaHref(item) {
  const params = caseParams(item);
  return `/qa?${params.toString()}`;
}

function caseWorkbenchHref(item) {
  const params = caseParams(item);
  return `/admin/rag-workbench?${params.toString()}`;
}

function caseParams(item) {
  const params = new URLSearchParams();
  params.set("kb_name", item.kb_name || (state.report?.kb_names || [])[0] || state.kbName || "default");
  if (item.query) params.set("question", item.query);
  return params;
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

function formatModified(value) {
  const timestamp = Number(value || 0) * 1000;
  if (!timestamp) return t("Unknown time");
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(timestamp));
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
$("eval-run-start").addEventListener("click", () => {
  startEvalRun().catch((error) => {
    $("eval-run-start").disabled = false;
    renderRunMessage(error.message);
    setStatus(error.message, "error");
  });
});
$("eval-run-suite").addEventListener("change", renderRunIdle);
$("eval-report-refresh").addEventListener("click", () => {
  loadRecentReports().catch((error) => setStatus(error.message, "error"));
});
$("eval-report-recents").addEventListener("click", (event) => {
  const card = event.target.closest("[data-report-index]");
  if (!card) return;
  loadRecentReport(Number(card.dataset.reportIndex));
});
$("eval-suite-history").addEventListener("click", (event) => {
  const selectButton = event.target.closest("[data-select-suite]");
  if (selectButton) {
    selectSuite(selectButton.dataset.selectSuite);
    return;
  }
  const runButton = event.target.closest("[data-run-suite]");
  if (runButton) {
    runSuite(runButton.dataset.runSuite).catch((error) => {
      $("eval-run-start").disabled = false;
      renderRunMessage(error.message);
      setStatus(error.message, "error");
    });
    return;
  }
  const loadButton = event.target.closest("[data-load-suite-report]");
  if (loadButton) {
    loadSuiteLatestReport(loadButton.dataset.loadSuiteReport);
  }
});

bindSharedApiToken($("eval-report-api-token"));
initI18n({ mount: ".top-actions" });
updateLinks();
renderEmpty();
loadEvalSuites().catch((error) => {
  $("eval-run-start").disabled = true;
  renderRunMessage(error.message);
});
loadRecentReports().catch((error) => {
  $("eval-report-recents-count").textContent = t("Recent reports unavailable");
  $("eval-report-recents").textContent = error.message;
  $("eval-report-recents").className = "eval-report-recents empty-state";
});
if (reportPath()) {
  loadReport().catch((error) => setStatus(error.message, "error"));
}
translatePage();
