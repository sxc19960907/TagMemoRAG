const configEl = document.getElementById("manual-library-config");
const config = JSON.parse(configEl?.textContent || "{}");

const state = {
  kbName: config.defaultKbName || "default",
  apiToken: sessionStorage.getItem("tagmemoragApiToken") || "",
  manuals: [],
  selectedManualId: null,
  libraryRoot: "",
  filters: { text: "", status: "all", searchable: "all", pending: "all" },
  rebuildTask: null,
  loading: false,
  suggestions: { upload: [], detail: [] },
};

const fields = [
  "title",
  "source_file",
  "brand",
  "product_category",
  "product_name",
  "product_model",
  "language",
  "version",
  "status",
  "tags",
  "notes",
];

const el = {
  status: document.getElementById("status-strip"),
  kbForm: document.getElementById("kb-form"),
  kbName: document.getElementById("kb-name"),
  token: document.getElementById("api-token"),
  rows: document.getElementById("manual-rows"),
  empty: document.getElementById("table-empty"),
  count: document.getElementById("manual-count"),
  root: document.getElementById("library-root"),
  filterText: document.getElementById("filter-text"),
  filterStatus: document.getElementById("filter-status"),
  filterSearchable: document.getElementById("filter-searchable"),
  filterPending: document.getElementById("filter-pending"),
  detailSubtitle: document.getElementById("detail-subtitle"),
  detailForm: document.getElementById("detail-form"),
  detailMessages: document.getElementById("detail-messages"),
  detailSuggestions: document.getElementById("detail-suggestions"),
  suggestDetailTags: document.getElementById("suggest-detail-tags"),
  acceptAllDetailTags: document.getElementById("accept-all-detail-tags"),
  validateDetail: document.getElementById("validate-detail"),
  replaceFile: document.getElementById("replace-file"),
  replaceFileButton: document.getElementById("replace-file-button"),
  disableManual: document.getElementById("disable-manual"),
  hardDeleteConfirm: document.getElementById("hard-delete-confirm"),
  hardDelete: document.getElementById("hard-delete"),
  uploadDialog: document.getElementById("upload-dialog"),
  openUpload: document.getElementById("open-upload"),
  closeUpload: document.getElementById("close-upload"),
  uploadForm: document.getElementById("upload-form"),
  uploadMessages: document.getElementById("upload-messages"),
  uploadSuggestions: document.getElementById("upload-suggestions"),
  suggestUploadTags: document.getElementById("suggest-upload-tags"),
  acceptAllUploadTags: document.getElementById("accept-all-upload-tags"),
  validateUpload: document.getElementById("validate-upload"),
  rebuild: document.getElementById("rebuild-library"),
};

el.kbName.value = state.kbName;
el.token.value = state.apiToken;

function headers(json = true) {
  const result = {};
  if (json) result["Content-Type"] = "application/json";
  if (state.apiToken) result.Authorization = `Bearer ${state.apiToken}`;
  return result;
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${config.apiBasePath || ""}${path}`, {
    ...options,
    headers: { ...(options.headers || {}) },
  });
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { message: text };
    }
  }
  if (!response.ok) {
    const message = body?.message || `${response.status} ${response.statusText}`;
    const detail = body?.detail ? ` ${formatDetail(body.detail)}` : "";
    throw new Error(`${body?.code ? `${body.code}: ` : ""}${message}${detail}`);
  }
  return body;
}

function formatDetail(detail) {
  if (!detail) return "";
  if (Array.isArray(detail.messages)) {
    return detail.messages.map((msg) => `${msg.field}: ${msg.message}`).join("; ");
  }
  return JSON.stringify(detail);
}

function setStatus(message, kind = "") {
  el.status.className = `status-strip ${kind}`.trim();
  el.status.textContent = message || "";
}

function selectedManual() {
  return state.manuals.find((manual) => manual.manual_id === state.selectedManualId) || null;
}

function manualMetadata(manual) {
  return { ...(manual?.metadata || {}) };
}

function tagsFromText(value) {
  return String(value || "")
    .split(/[,\n]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function tagsToText(tags) {
  return Array.isArray(tags) ? tags.join(", ") : "";
}

function normalizeTag(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function metadataFromForm(form, includeManualId = false) {
  const data = new FormData(form);
  let raw = {};
  const rawText = String(data.get("raw_json") || "").trim();
  if (rawText) raw = JSON.parse(rawText);
  const metadata = { ...raw };
  if (includeManualId) metadata.manual_id = String(data.get("manual_id") || "").trim();
  fields.forEach((field) => {
    if (!data.has(field)) return;
    metadata[field] = field === "tags" ? tagsFromText(data.get(field)) : String(data.get(field) || "").trim();
  });
  return metadata;
}

function uploadMetadataFromForm() {
  const data = new FormData(el.uploadForm);
  return {
    manual_id: String(data.get("manual_id") || "").trim(),
    title: String(data.get("title") || "").trim(),
    source_file: String(data.get("source_file") || "").trim(),
    product_category: String(data.get("product_category") || "").trim(),
    brand: String(data.get("brand") || "").trim(),
    product_name: String(data.get("product_name") || "").trim(),
    product_model: String(data.get("product_model") || "").trim(),
    language: String(data.get("language") || "").trim() || "unknown",
    version: String(data.get("version") || "").trim(),
    tags: tagsFromText(data.get("tags")),
    notes: String(data.get("notes") || "").trim(),
  };
}

function showMessages(container, messages, kind = "") {
  container.innerHTML = "";
  messages.forEach((message) => {
    const div = document.createElement("div");
    div.className = `message ${kind}`.trim();
    div.textContent = typeof message === "string" ? message : `${message.field || "metadata"}: ${message.message}`;
    container.appendChild(div);
  });
}

function suggestionNodes(scope) {
  const box = scope === "upload" ? el.uploadSuggestions : el.detailSuggestions;
  return {
    status: box.querySelector('[data-role="status"]'),
    list: box.querySelector('[data-role="list"]'),
    acceptAll: scope === "upload" ? el.acceptAllUploadTags : el.acceptAllDetailTags,
    suggest: scope === "upload" ? el.suggestUploadTags : el.suggestDetailTags,
  };
}

function setSuggestionStatus(scope, message, kind = "") {
  const nodes = suggestionNodes(scope);
  nodes.status.className = `suggestion-status ${kind}`.trim();
  nodes.status.textContent = message || "";
}

function renderSuggestions(scope) {
  const nodes = suggestionNodes(scope);
  const suggestions = state.suggestions[scope] || [];
  nodes.list.innerHTML = "";
  nodes.acceptAll.disabled = suggestions.length === 0 || (scope === "detail" && !selectedManual());
  suggestions.forEach((suggestion) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "suggestion-chip";
    chip.textContent = suggestion.tag;
    chip.title = suggestion.reason || "";
    chip.addEventListener("click", () => acceptSuggestion(scope, suggestion.tag));
    nodes.list.appendChild(chip);
  });
}

function clearSuggestions(scope) {
  state.suggestions[scope] = [];
  setSuggestionStatus(scope, "");
  renderSuggestions(scope);
}

async function suggestTags(scope) {
  const metadata = scope === "upload" ? uploadMetadataFromForm() : metadataFromForm(el.detailForm, true);
  const nodes = suggestionNodes(scope);
  nodes.suggest.disabled = true;
  setSuggestionStatus(scope, "Loading suggestions...");
  try {
    const body = await apiFetch("/manuals/tags/suggest", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ kb_name: state.kbName, metadata, limit: 8 }),
    });
    state.suggestions[scope] = body.suggestions || [];
    renderSuggestions(scope);
    setSuggestionStatus(scope, state.suggestions[scope].length ? "" : "No new tag suggestions.");
  } catch (error) {
    state.suggestions[scope] = [];
    renderSuggestions(scope);
    setSuggestionStatus(scope, error.message, "error");
  } finally {
    nodes.suggest.disabled = scope === "detail" && !selectedManual();
  }
}

function tagsTextarea(scope) {
  return scope === "upload" ? el.uploadForm.elements.tags : el.detailForm.elements.tags;
}

function acceptSuggestion(scope, tag) {
  const input = tagsTextarea(scope);
  input.value = tagsToText(dedupeTags([...tagsFromText(input.value), tag]));
  state.suggestions[scope] = (state.suggestions[scope] || []).filter(
    (suggestion) => normalizeTag(suggestion.tag) !== normalizeTag(tag),
  );
  renderSuggestions(scope);
}

function acceptAllSuggestions(scope) {
  const input = tagsTextarea(scope);
  const accepted = (state.suggestions[scope] || []).map((suggestion) => suggestion.tag);
  input.value = tagsToText(dedupeTags([...tagsFromText(input.value), ...accepted]));
  state.suggestions[scope] = [];
  renderSuggestions(scope);
}

function dedupeTags(tags) {
  const seen = new Set();
  const result = [];
  tags.forEach((tag) => {
    const normalized = normalizeTag(tag);
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    result.push(normalized);
  });
  return result;
}

async function loadManuals() {
  state.loading = true;
  setStatus(`Loading ${state.kbName}...`);
  renderTable();
  try {
    const body = await apiFetch(`/manual-library?kb_name=${encodeURIComponent(state.kbName)}`, {
      headers: headers(false),
    });
    state.manuals = body.manuals || [];
    state.libraryRoot = body.library_root || "";
    if (state.selectedManualId && !selectedManual()) state.selectedManualId = null;
    setStatus(`Loaded ${state.manuals.length} manuals from ${state.kbName}.`, "success");
  } catch (error) {
    state.manuals = [];
    state.libraryRoot = "";
    setStatus(error.message, "error");
  } finally {
    state.loading = false;
    render();
  }
}

function filteredManuals() {
  const text = state.filters.text.toLowerCase();
  return state.manuals.filter((manual) => {
    const haystack = [
      manual.manual_id,
      manual.title,
      manual.source_file,
      manual.product_model,
      manual.product_category,
    ]
      .join(" ")
      .toLowerCase();
    if (text && !haystack.includes(text)) return false;
    if (state.filters.status !== "all" && manual.status !== state.filters.status) return false;
    if (state.filters.searchable === "yes" && !manual.searchable) return false;
    if (state.filters.searchable === "no" && manual.searchable) return false;
    if (state.filters.pending === "yes" && !manual.rebuild_required) return false;
    if (state.filters.pending === "no" && manual.rebuild_required) return false;
    return true;
  });
}

function render() {
  renderTable();
  renderDetail();
}

function renderTable() {
  const rows = filteredManuals();
  el.root.textContent = state.libraryRoot ? `Root ${state.libraryRoot}` : "Root not loaded";
  el.count.textContent = `${rows.length} of ${state.manuals.length} manuals`;
  el.rows.innerHTML = "";
  rows.forEach((manual) => {
    const tr = document.createElement("tr");
    tr.dataset.manualId = manual.manual_id;
    tr.className = manual.manual_id === state.selectedManualId ? "selected" : "";
    tr.innerHTML = `
      <td>${badge(manual.status || "active", manual.status === "active" ? "ok" : "off")}</td>
      <td>${escapeHtml(manual.manual_id)}</td>
      <td>${escapeHtml(manual.title || "")}</td>
      <td>${escapeHtml(manual.source_file || "")}</td>
      <td>${escapeHtml(manual.product_category || "")}</td>
      <td>${escapeHtml(manual.product_model || "")}</td>
      <td>${escapeHtml(manual.language || "")}</td>
      <td>${escapeHtml(tagsToText(manual.tags))}</td>
      <td>${badge(manual.searchable ? "yes" : "no", manual.searchable ? "ok" : "off")}</td>
      <td>${manual.chunk_count ?? ""}</td>
      <td>${badge(manual.rebuild_required ? "required" : "clear", manual.rebuild_required ? "warn" : "ok")}</td>
      <td>${escapeHtml(shortDate(manual.updated_at))}</td>
    `;
    tr.addEventListener("click", () => {
      state.selectedManualId = manual.manual_id;
      clearSuggestions("detail");
      render();
    });
    el.rows.appendChild(tr);
  });
  el.empty.hidden = state.loading || rows.length > 0;
  if (!state.loading && rows.length === 0) {
    el.empty.textContent = state.manuals.length ? "No manuals match the current filters." : "No managed manuals found.";
  }
}

function renderDetail() {
  const manual = selectedManual();
  const disabled = !manual;
  [...el.detailForm.elements].forEach((input) => {
    input.disabled = disabled;
  });
  el.validateDetail.disabled = disabled;
  el.suggestDetailTags.disabled = disabled;
  el.acceptAllDetailTags.disabled = disabled || state.suggestions.detail.length === 0;
  el.replaceFileButton.disabled = disabled;
  el.replaceFile.disabled = disabled;
  el.disableManual.disabled = disabled;
  el.hardDelete.disabled = disabled || el.hardDeleteConfirm.value !== manual?.manual_id;
  el.hardDeleteConfirm.disabled = disabled;
  el.detailSubtitle.textContent = manual ? manual.manual_id : "Select a manual";
  if (!manual) {
    clearSuggestions("detail");
    return;
  }

  const metadata = manualMetadata(manual);
  fields.forEach((field) => {
    const input = el.detailForm.elements[field];
    if (!input) return;
    input.value = field === "tags" ? tagsToText(metadata.tags || manual.tags) : metadata[field] || manual[field] || "";
  });
  const raw = { ...metadata };
  fields.forEach((field) => delete raw[field]);
  delete raw.manual_id;
  el.detailForm.elements.raw_json.value = JSON.stringify(raw, null, 2);
}

function badge(text, kind) {
  return `<span class="badge ${kind}">${escapeHtml(text)}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
  ));
}

function shortDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

async function validateMetadata(metadata, mode, currentManualId, container) {
  const body = await apiFetch("/manuals/validate", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      kb_name: state.kbName,
      metadata,
      mode,
      current_manual_id: currentManualId || null,
    }),
  });
  const messages = body.messages || [];
  if (body.valid) {
    showMessages(container, ["Metadata is valid."], "success");
  } else {
    showMessages(container, messages, "error");
  }
  return body;
}

el.kbForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.kbName = el.kbName.value.trim() || "default";
  state.selectedManualId = null;
  loadManuals();
});

el.token.addEventListener("input", () => {
  state.apiToken = el.token.value.trim();
  if (state.apiToken) sessionStorage.setItem("tagmemoragApiToken", state.apiToken);
  else sessionStorage.removeItem("tagmemoragApiToken");
});

[
  [el.filterText, "text"],
  [el.filterStatus, "status"],
  [el.filterSearchable, "searchable"],
  [el.filterPending, "pending"],
].forEach(([node, key]) => {
  node.addEventListener("input", () => {
    state.filters[key] = node.value;
    renderTable();
  });
});

el.validateDetail.addEventListener("click", async () => {
  const manual = selectedManual();
  if (!manual) return;
  try {
    const metadata = metadataFromForm(el.detailForm, true);
    metadata.manual_id = manual.manual_id;
    await validateMetadata(metadata, "update", manual.manual_id, el.detailMessages);
  } catch (error) {
    showMessages(el.detailMessages, [error.message], "error");
  }
});

el.suggestDetailTags.addEventListener("click", () => suggestTags("detail"));
el.acceptAllDetailTags.addEventListener("click", () => acceptAllSuggestions("detail"));

el.detailForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const manual = selectedManual();
  if (!manual) return;
  try {
    const metadata = metadataFromForm(el.detailForm, true);
    metadata.manual_id = manual.manual_id;
    const validation = await validateMetadata(metadata, "update", manual.manual_id, el.detailMessages);
    if (!validation.valid) return;
    await apiFetch(`/manuals/${encodeURIComponent(manual.manual_id)}/metadata`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify({ kb_name: state.kbName, metadata }),
    });
    setStatus("Metadata saved. Rebuild is required before search reflects the change.", "warn");
    await loadManuals();
  } catch (error) {
    showMessages(el.detailMessages, [error.message], "error");
  }
});

el.replaceFileButton.addEventListener("click", async () => {
  const manual = selectedManual();
  const file = el.replaceFile.files?.[0];
  if (!manual || !file) {
    setStatus("Choose a replacement source file first.", "warn");
    return;
  }
  if (!confirm("Replace this manual source file? Anchors may need rebuild reconciliation.")) return;
  const form = new FormData();
  form.set("kb_name", state.kbName);
  form.set("file", file);
  try {
    await apiFetch(`/manuals/${encodeURIComponent(manual.manual_id)}/file`, {
      method: "PUT",
      headers: headers(false),
      body: form,
    });
    el.replaceFile.value = "";
    setStatus("Source file replaced. Rebuild is required before search reflects the change.", "warn");
    await loadManuals();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

let disableArmedFor = "";
el.disableManual.addEventListener("click", async () => {
  const manual = selectedManual();
  if (!manual) return;
  if (disableArmedFor !== manual.manual_id) {
    disableArmedFor = manual.manual_id;
    setStatus(`Click Disable again to disable ${manual.manual_id}. Disabled manuals remain on disk.`, "warn");
    return;
  }
  try {
    await apiFetch(`/manuals/${encodeURIComponent(manual.manual_id)}?kb_name=${encodeURIComponent(state.kbName)}`, {
      method: "DELETE",
      headers: headers(false),
    });
    disableArmedFor = "";
    setStatus("Manual disabled. Rebuild is required to remove it from search.", "warn");
    await loadManuals();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el.hardDeleteConfirm.addEventListener("input", renderDetail);
el.hardDelete.addEventListener("click", async () => {
  const manual = selectedManual();
  if (!manual || el.hardDeleteConfirm.value !== manual.manual_id) return;
  if (!confirm(`Permanently delete ${manual.manual_id} source and metadata files?`)) return;
  try {
    await apiFetch(
      `/manuals/${encodeURIComponent(manual.manual_id)}?kb_name=${encodeURIComponent(state.kbName)}&hard=true`,
      { method: "DELETE", headers: headers(false) },
    );
    state.selectedManualId = null;
    el.hardDeleteConfirm.value = "";
    setStatus("Manual hard deleted. Rebuild is required to clear search state.", "warn");
    await loadManuals();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

el.openUpload.addEventListener("click", () => {
  el.uploadMessages.innerHTML = "";
  clearSuggestions("upload");
  if (typeof el.uploadDialog.showModal === "function") el.uploadDialog.showModal();
  else el.uploadDialog.setAttribute("open", "");
});

el.closeUpload.addEventListener("click", () => el.uploadDialog.close());

el.validateUpload.addEventListener("click", async () => {
  try {
    const mode = new FormData(el.uploadForm).get("overwrite") ? "upsert" : "create";
    await validateMetadata(uploadMetadataFromForm(), mode, null, el.uploadMessages);
  } catch (error) {
    showMessages(el.uploadMessages, [error.message], "error");
  }
});

el.suggestUploadTags.addEventListener("click", () => suggestTags("upload"));
el.acceptAllUploadTags.addEventListener("click", () => acceptAllSuggestions("upload"));

el.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const metadata = uploadMetadataFromForm();
    const validationMode = new FormData(el.uploadForm).get("overwrite") ? "upsert" : "create";
    const validation = await validateMetadata(metadata, validationMode, null, el.uploadMessages);
    if (!validation.valid) return;
    const data = new FormData(el.uploadForm);
    const file = data.get("file");
    const form = new FormData();
    form.set("kb_name", state.kbName);
    form.set("metadata", JSON.stringify(metadata));
    form.set("overwrite", data.get("overwrite") ? "true" : "false");
    form.set("trigger_rebuild", data.get("trigger_rebuild") ? "true" : "false");
    form.set("file", file);
    const body = await apiFetch("/manuals", {
      method: "POST",
      headers: headers(false),
      body: form,
    });
    el.uploadDialog.close();
    el.uploadForm.reset();
    setStatus(body.rebuild_task ? "Manual uploaded and rebuild started." : "Manual uploaded. Rebuild is required before it is searchable.", "warn");
    if (body.rebuild_task) pollRebuild(body.rebuild_task.task_id);
    await loadManuals();
  } catch (error) {
    showMessages(el.uploadMessages, [error.message], "error");
  }
});

el.rebuild.addEventListener("click", async () => {
  try {
    const task = await apiFetch("/manual-library/rebuild", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ kb_name: state.kbName }),
    });
    pollRebuild(task.task_id);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

async function pollRebuild(taskId) {
  state.rebuildTask = taskId;
  el.rebuild.disabled = true;
  setStatus(`Rebuild ${taskId} is running...`, "warn");
  const tick = async () => {
    try {
      const task = await apiFetch(`/rebuild/${encodeURIComponent(taskId)}`, { headers: headers(false) });
      if (task.status === "running") {
        setTimeout(tick, 1000);
        return;
      }
      el.rebuild.disabled = false;
      state.rebuildTask = null;
      if (task.status === "done") {
        setStatus(`Rebuild completed for ${task.kb_name || state.kbName}.`, "success");
      } else {
        setStatus(`Rebuild failed: ${task.error || JSON.stringify(task)}`, "error");
      }
      await loadManuals();
    } catch (error) {
      el.rebuild.disabled = false;
      state.rebuildTask = null;
      setStatus(error.message, "error");
    }
  };
  tick();
}

renderDetail();
loadManuals();
