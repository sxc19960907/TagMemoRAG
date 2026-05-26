export const SHARED_API_TOKEN_KEY = "tagmemoragApiToken";

export function sharedApiToken() {
  try {
    return window.sessionStorage.getItem(SHARED_API_TOKEN_KEY) || "";
  } catch (_error) {
    return "";
  }
}

export function setSharedApiToken(value) {
  const token = String(value || "").trim();
  try {
    if (token) window.sessionStorage.setItem(SHARED_API_TOKEN_KEY, token);
    else window.sessionStorage.removeItem(SHARED_API_TOKEN_KEY);
  } catch (_error) {
    return;
  }
}

export function bindSharedApiToken(input) {
  if (!input) return "";
  input.value = sharedApiToken();
  input.addEventListener("input", () => setSharedApiToken(input.value));
  return input.value;
}

export function authHeadersFromToken(value) {
  const token = String(value || "").trim();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
