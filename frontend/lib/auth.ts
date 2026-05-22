/**
 * JWT storage helpers for NEXUS frontend.
 *
 * All localStorage access goes through these functions — never call
 * localStorage.getItem('nexus_jwt') directly in components or hooks.
 * Server-side rendering guard: all functions return null/void when
 * called outside a browser context.
 */

const TOKEN_KEY = 'nexus_jwt' as const

/**
 * Retrieve the stored JWT access token.
 *
 * @returns The JWT string, or null if not set or running server-side.
 */
export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_KEY)
}

/**
 * Store a JWT access token.
 *
 * @param token - The JWT string returned by POST /api/v1/auth/login.
 */
export function setToken(token: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(TOKEN_KEY, token)
}

/**
 * Remove the stored JWT access token.
 *
 * Called on logout or when the gateway returns 401.
 */
export function removeToken(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(TOKEN_KEY)
}

/**
 * Check whether the user currently has a stored token.
 *
 * Does not validate expiry — use this only for UI guard checks.
 * The gateway validates expiry on every request.
 *
 * @returns True if a token is present in localStorage.
 */
export function isAuthenticated(): boolean {
  return getToken() !== null
}