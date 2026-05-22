import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Sign in',
}

/**
 * Auth layout — full-screen centered, NO sidebar or topbar.
 * Wraps /login and /register pages.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}