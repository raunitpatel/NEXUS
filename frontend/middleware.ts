/**
 * Next.js Edge Middleware for NEXUS authentication.
 *
 * Intercepts all requests to protected routes. Reads the JWT from the
 * 'nexus_jwt' cookie (set during login in AGNT-020). Redirects
 * unauthenticated requests to /login.
 *
 * NOTE: Middleware runs on the Edge runtime and cannot access localStorage.
 * The login flow (AGNT-020) must persist the JWT as both localStorage AND
 * a cookie so middleware can read it.
 *
 * Exempt routes: /login, /register, /_next/*, /favicon.ico, /api/*
 */

import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/** Routes that do not require authentication. */
const PUBLIC_PATHS = ['/login', '/register']

/**
 * Edge middleware — redirects unauthenticated users to /login.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Allow public routes through
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p))
  if (isPublic) return NextResponse.next()

  // Allow Next.js internals and static files
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon') ||
    pathname.startsWith('/api')
  ) {
    return NextResponse.next()
  }

  // Check for JWT cookie (set by login flow in AGNT-020)
  const token = request.cookies.get('nexus_jwt')?.value
  if (!token) {
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('from', pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * Match all routes except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
}