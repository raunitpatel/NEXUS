/**
 * Typed API client for the NEXUS API Gateway.
 *
 * All backend requests go through apiFetch() — never call fetch() directly
 * in components or hooks. apiFetch injects the JWT Authorization header,
 * serializes JSON bodies, and handles 401 redirects to /login.
 *
 * Base URL is read from NEXT_PUBLIC_API_URL (default: http://localhost:8080).
 */

import { getToken, removeToken } from '@/lib/auth'
import type { ApiError } from '@/lib/types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080'

/**
 * Options for apiFetch — extends standard RequestInit with a typed body helper.
 */
export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  /** JSON-serializable request body. Automatically sets Content-Type: application/json. */
  body?: unknown
}

/**
 * Typed API fetch wrapper for the NEXUS Gateway.
 *
 * Automatically injects the JWT Bearer token from localStorage.
 * Throws ApiError on non-2xx responses.
 * Redirects to /login and clears the token on 401.
 *
 * @param path - API path starting with /api (e.g. '/api/v1/runs').
 * @param options - Fetch options including optional JSON body.
 * @returns Parsed JSON response typed as T.
 * @throws ApiError on non-2xx HTTP responses.
 *
 * @example
 * const runs = await apiFetch<Run[]>('/api/v1/runs')
 * const run  = await apiFetch<CreateRunResponse>('/api/v1/runs', {
 *   method: 'POST',
 *   body: { query: 'Research transformers' },
 * })
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { body, headers: extraHeaders, ...rest } = options

  const headers: Record<string, string> = {
    ...(extraHeaders as Record<string, string>),
  }

  // Inject JWT if available
  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // Serialize JSON body
  let serializedBody: string | undefined
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    serializedBody = JSON.stringify(body)
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers,
    body: serializedBody,
  })

  // Handle 401 — token expired or revoked
  if (response.status === 401) {
    removeToken()
    if (typeof window !== 'undefined') {
      window.location.href = '/login'
    }
    const error: ApiError = { detail: 'Not authenticated', status: 401 }
    throw error
  }

  // Handle other non-2xx responses
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const errorBody = await response.json()
      detail = errorBody.detail ?? detail
    } catch {
      // Response body was not JSON — use status text
    }
    const error: ApiError = { detail, status: response.status }
    throw error
  }

  // Parse response — handle 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}