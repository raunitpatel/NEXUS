/**
 * JWT token utility for the NEXUS frontend.
 * Manages localStorage persistence and the nexus_token cookie
 * that Edge Middleware reads for route protection.
 */

const TOKEN_KEY = "access_token";
const COOKIE_NAME = "nexus_token";
const COOKIE_MAX_AGE = 86400; // 24 hours

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
export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  document.cookie = `${COOKIE_NAME}=${token}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Lax`;
}

/**
 * Read the JWT from localStorage.
 * Returns null if running server-side or token is absent.
 */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Remove the JWT from localStorage and expire the cookie.
 */
export function removeToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`;
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