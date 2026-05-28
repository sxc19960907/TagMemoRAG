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
  kbChip: document.getElementById("readiness-kb-chip"),
  title: document.getElementById("readiness-title"),
  summary: document.getElementById("readiness-summary"),
  guidance: document.getElementById("readiness-guidance"),
  primaryAction: document.getElementById("readiness-primary-action"),
  actions: document.getElementById("readiness-actions"),
  progressLabel: document.getElementById("readiness-progress-label"),
  steps: document.getElementById("readiness-steps"),
  capabilities: document.getElementById("readiness-capabilities"),
  delivery: document.getElementById("readiness-delivery"),
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
  el.kbChip.textContent = `${t("KB")} ${body.kb_name || state.kbName}`;
  el.title.textContent = t(titleForStatus(status));
  el.summary.textContent = t(body.summary || "");
  el.guidance.textContent = t(guidanceForStatus(status));
  renderActions(body.primary_action || null, body.actions || []);
  renderSteps(body.cards || []);
  renderCapabilities(body.capabilities || []);
  renderDelivery(body.delivery || []);
  renderCards(body.cards || []);
  renderRecommendations(body.recommendations || []);
}

function renderActions(primaryAction, actions) {
  const items = [];
  if (primaryAction?.href) {
    items.push({ ...primaryAction, primary: true });
  }
  if (Array.isArray(actions)) {
    items.push(...actions.filter((action) => action?.href && action.href !== primaryAction?.href));
  }
  if (!items.length) {
    el.primaryAction.textContent = t("No action available yet.");
    el.actions.innerHTML = "";
    return;
  }
  const primary = items[0];
  el.primaryAction.innerHTML = `
    <a class="button-link primary-link readiness-primary-link" href="${escapeHtml(primary.href || "#")}">${escapeHtml(t(primary.label || "Open"))}</a>
    <p>${escapeHtml(primaryActionHelp(primary.label || ""))}</p>
  `;
  el.actions.innerHTML = items.slice(1, 4).map((action) => `
    <a class="button-link" href="${escapeHtml(action.href || "#")}">${escapeHtml(t(action.label || "Open"))}</a>
  `).join("");
}

function renderSteps(cards) {
  const byId = Object.fromEntries((Array.isArray(cards) ? cards : []).map((card) => [card.id, card]));
  const steps = [
    {
      id: "kb",
      number: "1",
      title: "Load the knowledge base",
      description: "Make sure the selected KB is available to the server.",
      card: byId.kb,
    },
    {
      id: "manuals",
      number: "2",
      title: "Index manuals",
      description: "Upload documents and rebuild so retrieval sees the latest content.",
      card: byId.manuals,
    },
    {
      id: "eval",
      number: "3",
      title: "Check retrieval quality",
      description: "Run or review browser evals before trusting user answers.",
      card: byId.eval,
    },
    {
      id: "qa",
      number: "4",
      title: "Start Q&A",
      description: "Open the user QA page and inspect cited sources.",
      card: byId.qa,
    },
  ];
  const completed = steps.filter((step) => step.card?.status === "ready").length;
  el.progressLabel.textContent = t("{done} of {total} steps ready", { done: completed, total: steps.length });
  el.steps.className = "readiness-steps";
  el.steps.innerHTML = steps.map(renderStep).join("");
}

function renderStep(step) {
  const status = step.card?.status || "unknown";
  return `
    <article class="readiness-step ${escapeHtml(status)}">
      <span class="readiness-step-number">${escapeHtml(step.number)}</span>
      <div>
        <div class="readiness-step-head">
          <h3>${escapeHtml(t(step.title))}</h3>
          <span class="status-pill ${statusClass(status)}">${escapeHtml(t(statusLabel(status)))}</span>
        </div>
        <p>${escapeHtml(t(step.description))}</p>
        ${step.card?.summary ? `<small>${escapeHtml(t(step.card.summary))}</small>` : ""}
      </div>
    </article>
  `;
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

function renderCapabilities(capabilities) {
  if (!Array.isArray(capabilities) || !capabilities.length) {
    el.capabilities.className = "readiness-capabilities empty-state";
    el.capabilities.textContent = t("No capability checks returned.");
    return;
  }
  el.capabilities.className = "readiness-capabilities";
  el.capabilities.innerHTML = capabilities.map(renderCapability).join("");
}

function renderCapability(capability) {
  const detail = capability.detail || {};
  const rows = capabilityDetailRows(capability.id, detail);
  const action = capability.action || {};
  return `
    <article class="readiness-capability ${escapeHtml(capability.status || "unknown")}">
      <div class="readiness-capability-head">
        <span class="status-pill ${statusClass(capability.status)}">${escapeHtml(t(statusLabel(capability.status)))}</span>
        <strong>${escapeHtml(t(capability.title || "Capability"))}</strong>
      </div>
      <p>${escapeHtml(t(capability.summary || ""))}</p>
      ${rows.length ? `<dl>${rows.join("")}</dl>` : ""}
      ${action.href ? `<a class="button-link compact" href="${escapeHtml(action.href)}">${escapeHtml(t(action.label || "Open"))}</a>` : ""}
    </article>
  `;
}

function renderDelivery(delivery) {
  if (!Array.isArray(delivery) || !delivery.length) {
    el.delivery.className = "readiness-delivery empty-state";
    el.delivery.textContent = t("No delivery checks returned.");
    return;
  }
  el.delivery.className = "readiness-delivery";
  el.delivery.innerHTML = delivery.map(renderDeliveryCheck).join("");
}

function renderDeliveryCheck(item) {
  const href = item.href || "";
  return `
    <article class="readiness-delivery-check ${escapeHtml(item.status || "unknown")}">
      <div class="readiness-delivery-head">
        <span class="status-pill ${statusClass(item.status)}">${escapeHtml(t(statusLabel(item.status)))}</span>
        <span>${escapeHtml(t(item.kind || "Delivery gate"))}</span>
      </div>
      <h3>${escapeHtml(t(item.title || "Delivery check"))}</h3>
      <p>${escapeHtml(t(item.summary || ""))}</p>
      ${item.command ? `<code>${escapeHtml(item.command)}</code>` : ""}
      ${href ? `<a class="button-link compact" href="${escapeHtml(href)}">${escapeHtml(t("Open related page"))}</a>` : ""}
    </article>
  `;
}

function capabilityDetailRows(id, detail) {
  const allow = {
    answer: ["enabled", "provider", "model", "api_key_env", "api_key_present"],
    embedding: ["provider", "model", "dimensions", "api_key_env", "api_key_present"],
    ocr: ["enabled", "provider", "language"],
    source_preview: ["enabled", "pdf_page_snapshots_enabled", "renderer_available", "source_preview_status", "page_snapshots_ready", "page_snapshots_failed"],
  }[id] || [];
  const rows = allow
    .filter((key) => detail[key] !== undefined && detail[key] !== null && detail[key] !== "")
    .map((key) => `<dt>${escapeHtml(t(humanizeKey(key)))}</dt><dd>${escapeHtml(formatValue(detail[key]))}</dd>`);
  if (Array.isArray(detail.commands) && detail.commands.length) {
    rows.push(
      `<dt>${escapeHtml(t("Commands"))}</dt><dd>${escapeHtml(detail.commands.map((item) => `${item.label}: ${item.available ? t("available") : t("missing")}`).join(", "))}</dd>`
    );
  }
  return rows;
}

function renderCard(card) {
  const detail = card.detail || {};
  const detailRows = Object.entries(detail)
    .filter(([, value]) => typeof value !== "object" || value === null)
    .map(([key, value]) => `<dt>${escapeHtml(humanizeKey(key))}</dt><dd>${escapeHtml(formatValue(value))}</dd>`)
    .join("");
  return `
    <article class="readiness-card ${escapeHtml(card.status || "unknown")}">
      <div class="readiness-card-head">
        <span class="status-pill ${statusClass(card.status)}">${escapeHtml(t(statusLabel(card.status)))}</span>
        <span>${escapeHtml(cardIcon(card.id))}</span>
      </div>
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
  el.recommendations.innerHTML = items.map((item, index) => `
    <article class="readiness-recommendation ${escapeHtml(item.severity || "info")}">
      <span class="readiness-recommendation-index">${index + 1}</span>
      <div>
        <span class="status-pill ${item.severity === "error" ? "needs-review" : item.severity === "warning" ? "in-progress" : "neutral"}">${escapeHtml(t(item.severity || "info"))}</span>
        <p>${escapeHtml(t(item.label || ""))}</p>
        ${item.href ? `<a class="button-link compact" href="${escapeHtml(item.href)}">${escapeHtml(t(item.action_label || "Open"))}</a>` : ""}
      </div>
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
  const labels = {
    loaded: "Loaded",
    build_id: "Build",
    node_count: "Indexed chunks",
    pending_changes: "Pending rebuild",
    dirty_manual_count: "Dirty manuals",
    missing_blob_count: "Missing files",
    failed_rebuild_jobs: "Failed jobs",
    active_rebuild_jobs: "Active jobs",
    current_build_id: "Current build",
    api_key_env: "API key env",
    api_key_present: "API key present",
    dimensions: "Dimensions",
    language: "Language",
    missing_commands: "Missing commands",
    pdf_page_snapshots_enabled: "Page snapshots",
    renderer_available: "Renderer available",
    source_preview_status: "Source preview",
    source_preview_message: "Preview note",
    page_snapshots_ready: "Page previews ready",
    page_snapshots_failed: "Page previews failed",
    has_latest_report: "Eval report",
    suite_id: "Eval suite",
    passed: "Passed",
    cases: "Cases",
    failed: "Failed",
  };
  return labels[key] || String(key || "").replaceAll("_", " ");
}

function formatValue(value) {
  if (value === true) return t("Yes");
  if (value === false) return t("No");
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function titleForStatus(status) {
  if (status === "ready") return "Ready to try Q&A";
  if (status === "needs_review") return "Almost ready";
  if (status === "not_ready") return "Finish setup before Q&A";
  return "Checking setup";
}

function guidanceForStatus(status) {
  if (status === "ready") return "The selected knowledge base is ready for a normal browser Q&A session.";
  if (status === "needs_review") return "You can inspect the system now, but one setup signal still needs attention.";
  if (status === "not_ready") return "Start with the recommended action, then return here to confirm the KB is ready.";
  return "Follow the checklist below to get from documents to grounded Q&A.";
}

function primaryActionHelp(label) {
  const help = {
    "Start Q&A": "Open the user-facing chat page and ask against this KB.",
    "Open Q&A": "Open the user-facing chat page and ask against this KB.",
    "Manual Library": "Add manuals, rebuild the KB, or resolve document issues.",
    "Review manuals": "Open Manual Library to resolve document or rebuild blockers.",
    "Open Eval Report": "Run or review retrieval checks before depending on answers.",
    "Open latest report": "Inspect the most recent eval failures and recommended fixes.",
    "Refresh readiness": "Reload the current setup signals.",
  };
  return t(help[label] || "Continue with the next setup task for this KB.");
}

function cardIcon(id) {
  const icons = {
    kb: "01",
    manuals: "02",
    eval: "03",
    qa: "04",
  };
  return icons[id] || "•";
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
