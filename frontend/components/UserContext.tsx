"use client"

import React, { createContext, useContext } from 'react'

type UserContextValue = {
  displayName: string
  initials: string
}

const UserContext = createContext<UserContextValue | undefined>(undefined)

export function UserProvider({
  children,
  displayName,
  initials,
}: {
  children: React.ReactNode
  displayName: string
  initials: string
}) {
  return (
    <UserContext.Provider value={{ displayName, initials }}>
      {children}
    </UserContext.Provider>
  )
}

export function useUser() {
  const ctx = useContext(UserContext)
  if (!ctx) return { displayName: 'User', initials: 'U' }
  return ctx
}
