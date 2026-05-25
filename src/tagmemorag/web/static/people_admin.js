const configEl = document.getElementById("people-admin-config");
const config = configEl ? JSON.parse(configEl.textContent || "{}") : {};

const state = {
  kbName: config.defaultKbName || "default",
  keys: [],
  selectedId: "",
};

const el = {
  kbForm: document.getElementById("people-kb-form"),
  kbName: document.getElementById("people-kb-name"),
  token: document.getElementById("people-api-token"),
  status: document.getElementById("people-status"),
  authMode: document.getElementById("people-auth-mode"),
  authBackend: document.getElementById("people-auth-backend"),
  activeCount: document.getElementById("people-active-count"),
  totalCount: document.getElementById("people-total-count"),
  adminCount: document.getElementById("people-admin-count"),
  revokedCount: document.getElementById("people-revoked-count"),
  globalRate: document.getElementById("people-global-rate"),
  rows: document.getElementById("people-key-rows"),
  refresh: document.getElementById("people-refresh"),
  detailSubtitle: document.getElementById("people-detail-subtitle"),
  detailList: document.getElementById("people-detail-list"),
  publicPaths: document.getElementById("people-public-paths"),
  generateCommand: document.getElementById("people-generate-command"),
  workbench: document.getElementById("people-workbench"),
  manualLibrary: document.getElementById("people-manual-library"),
};

function headers() {
  const token = el.token.value.trim();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(message, kind = "") {
  el.status.textContent = message || "";
  el.status.className = kind ? `status-strip ${kind}` : "status-strip";
}

function updateLinks() {
  const kb = encodeURIComponent(state.kbName || "default");
  el.workbench.href = `/admin/rag-workbench?kb_name=${kb}`;
  el.manualLibrary.href = `/admin/manual-library?kb_name=${kb}`;
  el.generateCommand.textContent = `python -m tagmemorag auth generate-key --id support-a --scopes search --kb ${state.kbName || "default"} --rate 100`;
}

async function loadAccessSummary() {
  setStatus("Loading access summary...");
  el.refresh.disabled = true;
  try {
    const response = await fetch("/admin/people/access-summary", { headers: headers() });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.message || `HTTP ${response.status}`);
    }
    renderSummary(body);
    setStatus("Access summary loaded.", "success");
  } catch (error) {
    renderError(error);
    setStatus(error.message || "Access summary failed.", "error");
  } finally {
    el.refresh.disabled = false;
  }
}

function renderSummary(body) {
  const summary = body.summary || {};
  state.keys = Array.isArray(body.keys) ? body.keys : [];
  el.authMode.textContent = body.auth_enabled ? "Enabled" : "Disabled";
  el.authBackend.textContent = `backend=${body.backend || "-"}`;
  el.activeCount.textContent = String(summary.active_keys ?? 0);
  el.totalCount.textContent = `${summary.total_keys ?? state.keys.length} total`;
  el.adminCount.textContent = String(summary.admin_keys ?? 0);
  el.revokedCount.textContent = `${summary.revoked_keys ?? 0} revoked`;
  el.globalRate.textContent = String(body.global_max_rate_limit_per_minute ?? "-");
  renderPublicPaths(body.public_paths || []);
  renderRows();
  const selected = state.keys.find((item) => item.id === state.selectedId) || state.keys[0];
  renderDetail(selected || null);
}

function renderPublicPaths(paths) {
  if (!Array.isArray(paths) || paths.length === 0) {
    el.publicPaths.className = "people-chip-list empty-state";
    el.publicPaths.textContent = "No public paths configured.";
    return;
  }
  el.publicPaths.className = "people-chip-list";
  el.publicPaths.innerHTML = paths.map((path) => `<span class="badge off">${escapeHtml(path)}</span>`).join("");
}

function renderRows() {
  if (state.keys.length === 0) {
    el.rows.innerHTML = '<tr><td colspan="6" class="empty-state">No API-key identities are configured.</td></tr>';
    return;
  }
  el.rows.innerHTML = state.keys.map(renderRow).join("");
  el.rows.querySelectorAll("tr[data-key-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedId = row.dataset.keyId || "";
      renderRows();
      renderDetail(state.keys.find((item) => item.id === state.selectedId) || null);
    });
  });
}

function renderRow(item) {
  const isSelected = item.id === state.selectedId;
  const statusClass = item.status === "active" ? "ok" : "off";
  const rate = item.rate_limit_per_minute == null ? "default" : `${item.rate_limit_per_minute}/min`;
  return `
    <tr data-key-id="${escapeHtml(item.id)}" class="${isSelected ? "selected" : ""}">
      <td>
        <strong>${escapeHtml(item.label || item.id)}</strong>
        <small>${escapeHtml(item.id)}</small>
      </td>
      <td><span class="badge ${statusClass}">${escapeHtml(item.status || "active")}</span></td>
      <td>${renderChips(item.scopes)}</td>
      <td>${renderKbAccess(item.kb_allowlist)}</td>
      <td>${escapeHtml(rate)}</td>
      <td>${escapeHtml(formatDate(item.last_used_at))}</td>
    </tr>
  `;
}

function renderChips(values) {
  if (!Array.isArray(values) || values.length === 0) return '<span class="muted">none</span>';
  return `<div class="people-chip-list">${values.map((value) => `<span class="badge">${escapeHtml(value)}</span>`).join("")}</div>`;
}

function renderKbAccess(values) {
  if (!Array.isArray(values) || values.length === 0 || values.includes("*")) {
    return '<span class="badge ok">All KBs</span>';
  }
  return renderChips(values);
}

function renderDetail(item) {
  if (!item) {
    state.selectedId = "";
    el.detailSubtitle.textContent = "No access identity selected";
    el.detailList.innerHTML = "<dt>Status</dt><dd class=\"muted\">No configured API keys.</dd>";
    return;
  }
  state.selectedId = item.id;
  el.detailSubtitle.textContent = item.label || item.id;
  el.detailList.innerHTML = `
    <dt>ID</dt><dd>${escapeHtml(item.id)}</dd>
    <dt>Label</dt><dd>${escapeHtml(item.label || "-")}</dd>
    <dt>Status</dt><dd><span class="badge ${item.status === "active" ? "ok" : "off"}">${escapeHtml(item.status)}</span></dd>
    <dt>Scopes</dt><dd>${renderChips(item.scopes)}</dd>
    <dt>KB access</dt><dd>${renderKbAccess(item.kb_allowlist)}</dd>
    <dt>Rate</dt><dd>${escapeHtml(item.rate_limit_per_minute == null ? "default" : `${item.rate_limit_per_minute}/min`)}</dd>
    <dt>Created</dt><dd>${escapeHtml(formatDate(item.created_at))}</dd>
    <dt>Last used</dt><dd>${escapeHtml(formatDate(item.last_used_at))}</dd>
  `;
}

function renderError(error) {
  state.keys = [];
  el.rows.innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHtml(error.message || "Unable to load access summary.")}</td></tr>`;
  renderDetail(null);
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

el.kbForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.kbName = el.kbName.value.trim() || "default";
  updateLinks();
  setStatus(`KB set to ${state.kbName}.`);
});

el.refresh.addEventListener("click", loadAccessSummary);
updateLinks();
loadAccessSummary();
