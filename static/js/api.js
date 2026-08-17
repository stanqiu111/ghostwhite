/* Shared frontend auth + fetch helper.
 *
 * Token model: login stores `access_token` (JWT, 1h) and `refresh_token`
 * (7d) in localStorage. `access_token` is the ONLY access key we read;
 * the legacy `access` / `refresh` keys are cleared on logout but never read.
 *
 * apiFetch() is the resilient entry point: it attaches the bearer token when
 * present, always sends the CSRF token + same-origin cookies (so a valid
 * Django session still authenticates the request even if the token is stale),
 * and on a token-expiry 401 it transparently refreshes the access token once
 * and retries the original request.
 */

const TOKEN_KEYS = {
  access: "access_token",
  refresh: "refresh_token",
  // legacy keys we no longer write, but still purge on logout for safety
  legacy: ["access", "refresh"],
};
const REFRESH_URL = "/api/authors/token/refresh/";
const LOGIN_URL = "/authors/auth/";

function getCSRFToken() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

function getAccessToken() {
  return localStorage.getItem(TOKEN_KEYS.access);
}

function getRefreshToken() {
  return localStorage.getItem(TOKEN_KEYS.refresh);
}

/* Clear every token variant — current and legacy — plus identity keys. */
function clearTokens() {
  [TOKEN_KEYS.access, TOKEN_KEYS.refresh, ...TOKEN_KEYS.legacy, "user_id", "username"]
    .forEach((k) => localStorage.removeItem(k));
}

/* Header builders kept for existing call sites. Both read `access_token`. */
function getHeaders() {
  const token = getAccessToken();
  return {
    "X-CSRFToken": getCSRFToken(),
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
    ...(token && { Authorization: `Bearer ${token}` }),
  };
}

function getHeadersWithNoContentType() {
  // used for FormData / file uploads where the browser sets the boundary
  const token = getAccessToken();
  return {
    ...(token && { Authorization: `Bearer ${token}` }),
  };
}

/* Exchange the refresh token for a fresh access token. Returns the new access
   token string, or null if refresh is impossible/failed. Concurrent callers
   (e.g. several pollers hitting 401 at once) share one in-flight request. */
let _refreshInFlight = null;
function refreshAccessToken() {
  if (_refreshInFlight) return _refreshInFlight;
  const refresh = getRefreshToken();
  if (!refresh) return Promise.resolve(null);

  _refreshInFlight = (async () => {
    try {
      const res = await fetch(REFRESH_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body: JSON.stringify({ refresh }),
      });
      if (!res.ok) return null;
      const data = await res.json().catch(() => null);
      if (data && data.access) {
        localStorage.setItem(TOKEN_KEYS.access, data.access);
        // ROTATE_REFRESH_TOKENS is off, but honour a rotated refresh if present
        if (data.refresh) localStorage.setItem(TOKEN_KEYS.refresh, data.refresh);
        return data.access;
      }
      return null;
    } catch (e) {
      return null;
    }
  })();
  _refreshInFlight.finally(() => { _refreshInFlight = null; });
  return _refreshInFlight;
}

/* Merge caller headers with the auth/CSRF defaults. `authOverride` forces a
   specific bearer token (used on retry with a freshly refreshed token). */
function buildRequestHeaders(options, authOverride) {
  const h = new Headers(options.headers || {});
  if (!h.has("X-CSRFToken")) h.set("X-CSRFToken", getCSRFToken());
  if (!h.has("X-Requested-With")) h.set("X-Requested-With", "XMLHttpRequest");

  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!isForm && options.body != null && !h.has("Content-Type")) {
    h.set("Content-Type", "application/json");
  }
  if (authOverride) {
    h.set("Authorization", `Bearer ${authOverride}`);
  } else if (!h.has("Authorization")) {
    const token = getAccessToken();
    if (token) h.set("Authorization", `Bearer ${token}`);
  }
  return h;
}

/*
 * Resilient same-origin fetch. Drop-in for fetch() at authenticated call sites.
 *
 * options: standard fetch init, plus:
 *   redirectOnAuthFailure: if true, send the user to the login page when the
 *                          refresh token is also dead (default false, so
 *                          background pollers don't yank the page away).
 *
 * Returns the Response (the caller still inspects status/body).
 */
async function apiFetch(url, options = {}) {
  const init = { ...options, credentials: options.credentials || "same-origin" };
  // Did the outgoing request carry a bearer token (from the caller or storage)?
  const sentBearer =
    new Headers(options.headers || {}).has("Authorization") || !!getAccessToken();

  init.headers = buildRequestHeaders(options);
  let res = await fetch(url, init);

  // A 401 after we presented a bearer token almost always means the access
  // token expired — try one refresh + retry. (If we never sent a token, a 401
  // is a real auth/permission failure, not staleness, so leave it alone.)
  if (res.status === 401 && sentBearer && getRefreshToken()) {
    const fresh = await refreshAccessToken();
    if (fresh) {
      const retry = { ...options, credentials: options.credentials || "same-origin" };
      retry.headers = buildRequestHeaders(options, fresh);
      res = await fetch(url, retry);
    } else {
      // Refresh token invalid/expired: stale creds are useless — purge them.
      clearTokens();
      if (options.redirectOnAuthFailure) {
        window.location.href = LOGIN_URL;
      }
    }
  }
  return res;
}
