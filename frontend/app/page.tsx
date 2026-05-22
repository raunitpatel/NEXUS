/**
 * Root page — redirects to /dashboard.
 *
 * Unauthenticated users are caught by middleware.ts before reaching here
 * and redirected to /login.
 */

import { redirect } from 'next/navigation'

export default function RootPage() {
  redirect('/dashboard')
}