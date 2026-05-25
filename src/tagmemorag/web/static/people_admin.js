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
  lifecycle: document.getElementById("people-lifecycle"),
  publicPaths: document.getElementById("people-public-paths"),
  generateCommand: document.getElementById("people-generate-command"),
  generateForm: document.getElementById("people-generate-form"),
  newId: document.getElementById("people-new-id"),
  newLabel: document.getElementById("people-new-label"),
  newScopes: document.getElementById("people-new-scopes"),
  newKbs: document.getElementById("people-new-kbs"),
  newRate: document.getElementById("people-new-rate"),
  newPrefix: document.getElementById("people-new-prefix"),
  generateSubmit: document.getElementById("people-generate-submit"),
  generationResult: document.getElementById("people-generation-result"),
  plaintextKey: document.getElementById("people-plaintext-key"),
  configJson: document.getElementById("people-config-json"),
  copyPlaintext: document.getElementById("people-copy-plaintext"),
  copyConfig: document.getElementById("people-copy-config"),
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
  if (!el.newKbs.value.trim()) el.newKbs.value = state.kbName || "default";
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

async function generateAccessKey(event) {
  event.preventDefault();
  const keyId = el.newId.value.trim();
  if (!keyId) {
    setStatus("Enter an ID for the new access key.", "error");
    return;
  }
  const payload = {
    id: keyId,
    label: el.newLabel.value.trim(),
    scopes: splitList(el.newScopes.value, ["search"]),
    kb_allowlist: splitList(el.newKbs.value, [state.kbName || "default"]),
    rate_limit_per_minute: el.newRate.value ? Number(el.newRate.value) : null,
    prefix: el.newPrefix.value || "tmr_live_",
  };
  el.generateSubmit.disabled = true;
  setStatus("Generating one-time key...");
  try {
    const response = await fetch("/admin/people/access-keys/generate", {
      method: "POST",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.message || `HTTP ${response.status}`);
    }
    renderGeneratedKey(body);
    setStatus("One-time key generated. Copy it before leaving this page.", "success");
  } catch (error) {
    setStatus(error.message || "Key generation failed.", "error");
  } finally {
    el.generateSubmit.disabled = false;
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
    renderLifecycle(null);
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
  renderLifecycle(item);
}

function renderError(error) {
  state.keys = [];
  el.rows.innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHtml(error.message || "Unable to load access summary.")}</td></tr>`;
  renderDetail(null);
}

function renderGeneratedKey(body) {
  el.generationResult.hidden = false;
  el.plaintextKey.value = body.plaintext_key || "";
  el.configJson.value = body.config_json || JSON.stringify(body.config_entry || {}, null, 2);
}

function renderLifecycle(item) {
  if (!item) {
    el.lifecycle.className = "people-lifecycle empty-state";
    el.lifecycle.textContent = "Select an access identity to prepare revoke or rotation steps.";
    return;
  }
  const revokeEntry = safeLifecycleEntry(item, { revoked: true });
  const replacementId = `${item.id}-replacement`;
  const scopes = listForInput(item.scopes, "search");
  const kbs = listForInput(item.kb_allowlist, state.kbName || "default");
  const rate = item.rate_limit_per_minute == null ? "default" : `${item.rate_limit_per_minute}/min`;
  el.lifecycle.className = "people-lifecycle";
  el.lifecycle.innerHTML = `
    <div class="people-lifecycle-actions">
      <button id="people-template-key" type="button">Use as template</button>
      <button id="people-copy-revoke" type="button">Copy revoke config</button>
    </div>
    <div class="people-lifecycle-block">
      <strong>Revoke config entry</strong>
      <p class="muted">Set the old key to revoked in config. The original hash is intentionally not shown here.</p>
      <textarea id="people-revoke-json" readonly rows="7">${escapeHtml(JSON.stringify(revokeEntry, null, 2))}</textarea>
    </div>
    <div class="people-lifecycle-block">
      <strong>Rotate plan</strong>
      <ol class="people-rotate-plan">
        <li>Use this key as a template and generate <code>${escapeHtml(replacementId)}</code>.</li>
        <li>Keep scopes <code>${escapeHtml(scopes)}</code>, KB access <code>${escapeHtml(kbs)}</code>, and rate <code>${escapeHtml(rate)}</code>.</li>
        <li>Add the generated config entry, deploy or reload config, then revoke <code>${escapeHtml(item.id)}</code>.</li>
      </ol>
    </div>
  `;
  document.getElementById("people-template-key").addEventListener("click", () => useKeyAsTemplate(item));
  document.getElementById("people-copy-revoke").addEventListener("click", () => {
    copyValue(document.getElementById("people-revoke-json"), "Revoke config");
  });
}

function safeLifecycleEntry(item, extra = {}) {
  return {
    id: item.id,
    label: item.label || "",
    kb_allowlist: Array.isArray(item.kb_allowlist) ? item.kb_allowlist : [],
    scopes: Array.isArray(item.scopes) ? item.scopes : [],
    rate_limit_per_minute: item.rate_limit_per_minute ?? null,
    ...extra,
  };
}

function useKeyAsTemplate(item) {
  el.newId.value = `${item.id}-replacement`;
  el.newLabel.value = item.label ? `${item.label} replacement` : "";
  el.newScopes.value = listForInput(item.scopes, "search");
  el.newKbs.value = listForInput(item.kb_allowlist, state.kbName || "default");
  el.newRate.value = item.rate_limit_per_minute == null ? "" : String(item.rate_limit_per_minute);
  el.newId.focus();
  setStatus(`Generation form prefilled from ${item.id}.`, "success");
}

function listForInput(values, fallback) {
  if (!Array.isArray(values) || values.length === 0) return fallback;
  return values.join(",");
}

function splitList(value, fallback) {
  const items = String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items : fallback;
}

async function copyValue(textarea, label) {
  const value = textarea.value;
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    setStatus(`${label} copied.`, "success");
  } catch (_error) {
    textarea.focus();
    textarea.select();
    setStatus(`${label} selected for copying.`, "warn");
  }
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
el.generateForm.addEventListener("submit", generateAccessKey);
el.copyPlaintext.addEventListener("click", () => copyValue(el.plaintextKey, "Plaintext key"));
el.copyConfig.addEventListener("click", () => copyValue(el.configJson, "Config JSON"));
updateLinks();
loadAccessSummary();
