import { NextRequest, NextResponse } from "next/server";

/** Protected route prefixes — middleware blocks unauthenticated access. */
const PROTECTED_PREFIXES = [
  "/dashboard",
  "/runs",
  "/history",
  "/memory",
  "/observability",
  "/agents",
];

/** Public routes — always accessible. */
const PUBLIC_PATHS = ["/login", "/register", "/terms", "/privacy"];

/**
 * Decode JWT payload without verifying signature.
 * Used only for lightweight Edge Runtime expiration checks.
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");

    if (parts.length !== 3) {
      return null;
    }

    const base64 = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/");

    const json = atob(base64);

    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Check whether token contains a valid future exp claim.
 * NOTE: Signature is NOT verified here.
 */
function isTokenValid(token: string): boolean {
  const payload = decodeJwtPayload(token);

  if (!payload || typeof payload.exp !== "number") {
    return false;
  }

  return payload.exp > Date.now() / 1000;
}

/**
 * Next.js Edge Middleware
 */
export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  const token = request.cookies.get("nexus_token")?.value;
  const authenticated = token && isTokenValid(token);

  /**
   * Handle root route "/"
   *
   * If logged in:
   *   / -> /dashboard
   *
   * If not logged in:
   *   / -> /login
   */
  if (pathname === "/") {
    const redirectUrl = authenticated
      ? new URL("/dashboard", request.url)
      : new URL("/login", request.url);

    return NextResponse.redirect(redirectUrl);
  }

  /**
   * Allow public routes
   */
  const isPublicRoute = PUBLIC_PATHS.some(
    (path) =>
      pathname === path ||
      pathname.startsWith(path + "/")
  );

  if (isPublicRoute) {
    return NextResponse.next();
  }

  /**
   * Check whether current route is protected
   */
  const isProtectedRoute = PROTECTED_PREFIXES.some(
    (prefix) =>
      pathname === prefix ||
      pathname.startsWith(prefix + "/")
  );

  /**
   * Non-protected routes are allowed
   */
  if (!isProtectedRoute) {
    return NextResponse.next();
  }

  /**
   * Redirect unauthenticated users
   */
  if (!authenticated) {
    const loginUrl = new URL("/login", request.url);

    loginUrl.searchParams.set(
      "reason",
      token ? "expired" : "unauthenticated"
    );

    return NextResponse.redirect(loginUrl);
  }

  /**
   * Allow authenticated users
   */
  return NextResponse.next();
}

/**
 * Run middleware only on page routes.
 * Skip:
 * - API routes
 * - Next.js internals
 * - Static assets
 * - Images
 */
export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};