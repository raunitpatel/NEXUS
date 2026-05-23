// frontend/app/(app)/layout.tsx
'use client'

/**
 * Authenticated app layout — renders Sidebar with decoded JWT user data.
 * All protected pages (dashboard, runs, history, etc.) use this layout.
 */


import type { Metadata } from 'next'
import { useEffect, useState } from 'react'
import { Sidebar } from '@/components/ui/Sidebar'
import { UserProvider } from '@/components/UserContext'
import { getToken, subscribeTokenChange } from '@/lib/auth'



interface JwtPayload {
  sub: string
  jti: string
  exp: number
  iat: number
  display_name?: string
}

function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(payload)) as JwtPayload
  } catch {
    return null
  }
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [displayName, setDisplayName] = useState('User')
  const [initials, setInitials] = useState('U')

  useEffect(() => {
    const updateUserFromToken = (token: string | null) => {
      if (!token) {
        setDisplayName('User')
        setInitials('U')
        return
      }

      const payload = decodeJwtPayload(token)
      if (!payload) return

      const name = payload.display_name ?? `User ${payload.sub.slice(0, 4)}`
      setDisplayName(name)
      setInitials(getInitials(name))
    }

    updateUserFromToken(getToken())
    const unsubscribe = subscribeTokenChange(updateUserFromToken)
    return unsubscribe
  }, [])

  return (
    <UserProvider displayName={displayName} initials={initials}>
      <div className="flex h-screen overflow-hidden">
        <Sidebar displayName={displayName} initials={initials} />
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {children}
        </main>
      </div>
    </UserProvider>
  )
}
