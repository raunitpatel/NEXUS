/**
 * JWT token utility for the NEXUS frontend.
 * Manages localStorage persistence and the nexus_token cookie
 * that Edge Middleware reads for route protection.
 */

const TOKEN_KEY = "access_token";
const COOKIE_NAME = "nexus_token";
const COOKIE_MAX_AGE = 86400; // 24 hours
const TOKEN_CHANGE_EVENT = "nexus-token-changed";

/**
 * Decode the payload of a JWT without verifying the signature.
 * Used only for reading the `exp` claim client-side.
 */
function decodePayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

/**
 * Persist the JWT to localStorage and set the nexus_token cookie
 * so Edge Middleware can read it for route protection.
 */
function dispatchTokenChange(token: string | null): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(TOKEN_CHANGE_EVENT, { detail: { token } }))
}

export function subscribeTokenChange(listener: (token: string | null) => void): () => void {
  if (typeof window === "undefined") return () => {}

  const handler = (event: Event) => {
    const detail = (event as CustomEvent<{ token: string | null }>).detail
    listener(detail?.token ?? null)
  }

  window.addEventListener(TOKEN_CHANGE_EVENT, handler)
  return () => window.removeEventListener(TOKEN_CHANGE_EVENT, handler)
}

export function setToken(token: string, remember = true): void {
  if (typeof window === "undefined") return;

  if (remember) {
    localStorage.setItem(TOKEN_KEY, token);
    sessionStorage.removeItem(TOKEN_KEY);
    document.cookie = `${COOKIE_NAME}=${token}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Lax`;
  } else {
    sessionStorage.setItem(TOKEN_KEY, token);
    localStorage.removeItem(TOKEN_KEY);
    document.cookie = `${COOKIE_NAME}=${token}; path=/; SameSite=Lax`;
  }

  dispatchTokenChange(token)
}

/**
 * Read the JWT from browser storage.
 * Returns null if running server-side or token is absent.
 */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const fromStorage = localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY);
  if (fromStorage) return fromStorage;

  // Fallback: try to read the nexus_token cookie (set by setToken)
  const match = document.cookie.match(new RegExp('(?:^|; )' + COOKIE_NAME + '=([^;]*)'))
  if (match) return decodeURIComponent(match[1])
  return null
}

/**
 * Remove the JWT from localStorage and expire the cookie.
 */
export function removeToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`;
  dispatchTokenChange(null)
}

/**
 * Return true if the provided JWT has a future `exp` claim.
 * Does NOT verify the signature — used for redirect decisions only.
 */
export function isTokenValid(token: string): boolean {
  const payload = decodePayload(token);
  if (!payload || typeof payload.exp !== "number") return false;
  return payload.exp > Date.now() / 1000;
}