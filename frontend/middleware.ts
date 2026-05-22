import { NextRequest, NextResponse } from "next/server";

/** Protected route prefixes — middleware blocks unauthenticated access. */
const PROTECTED_PREFIXES = [
  '/dashboard',
  '/orchestrator',
  '/runs',
  '/history',
  '/memory',
  '/observability',
  '/agents',
]

/** Public routes — always accessible, even with a valid token. */
const PUBLIC_PATHS = ["/login", "/register", "/terms", "/privacy", "/"];

/**
 * Decode the payload of a JWT without verifying the signature.
 * Used only to check the `exp` claim in the Edge Runtime.
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64);
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Return true if the JWT has a future `exp` claim.
 * Does NOT verify the signature — redirect decisions only.
 */
function isTokenValid(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return false;
  return payload.exp > Date.now() / 1000;
}

/**
 * Next.js Edge Middleware.
 * Redirects unauthenticated (or expired-token) users away from
 * protected routes to /login.
 */
export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  // Allow public paths through unconditionally
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"))) {
    return NextResponse.next();
  }

  // Check if this is a protected route
  const isProtected = PROTECTED_PREFIXES.some((prefix) =>
    pathname.startsWith(prefix)
  );

  if (!isProtected) {
    return NextResponse.next();
  }

  // Read the token from the cookie bridge set by auth.ts:setToken()
  const token = request.cookies.get("nexus_token")?.value;

  if (!token || !isTokenValid(token)) {
    const loginUrl = new URL("/login", request.url);
    if (!token) {
      loginUrl.searchParams.set("reason", "unauthenticated");
    } else {
      loginUrl.searchParams.set("reason", "expired");
    }
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

/** Only run middleware on page routes — skip API routes, static files, images. */
export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};