'use client'

import { useEffect } from 'react'
import Link from 'next/link'

interface ErrorPageProps {
  error: Error & { digest?: string }
  reset: () => void
}

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    console.error('[NEXUS] Unhandled error:', error)
  }, [error])

  return (
    <div className="min-h-screen bg-nexus-bg flex items-center justify-center px-6">
      <div className="text-center max-w-md">
        {/* Icon */}
        <div className="w-16 h-16 bg-[#FDECEA] rounded-[14px] flex items-center justify-center mx-auto mb-5">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="12" stroke="#E24B4A" strokeWidth="2"/>
            <path d="M16 10v8" stroke="#E24B4A" strokeWidth="2.5" strokeLinecap="round"/>
            <circle cx="16" cy="21.5" r="1.5" fill="#E24B4A"/>
          </svg>
        </div>

        {/* Wordmark */}
        <div className="flex items-center justify-center gap-2 mb-4">
          <div className="w-6 h-6 bg-nexus-accent rounded-[5px] flex items-center justify-center">
            <svg viewBox="0 0 14 14" fill="none" className="w-[14px] h-[14px]">
              <rect x="1" y="1" width="5" height="5" rx="1" fill="white"/>
              <rect x="8" y="1" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
              <rect x="1" y="8" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
              <rect x="8" y="8" width="5" height="5" rx="1" fill="white" opacity="0.3"/>
            </svg>
          </div>
          <span className="text-[14px] font-bold text-nexus-dark tracking-[0.06em]">NEXUS</span>
        </div>

        <h1 className="text-[22px] font-semibold text-nexus-dark mb-2">Something went wrong</h1>
        <p className="text-[13.5px] text-nexus-muted mb-6 leading-[1.6]">
          An unexpected error occurred. Our system has been notified.
          {error.digest && (
            <span className="block mt-1 font-mono text-[12px] text-nexus-subtle">Error ID: {error.digest}</span>
          )}
        </p>

        <div className="flex items-center justify-center gap-3">
          <button
            onClick={reset}
            className="bg-nexus-accent hover:bg-nexus-accent-hover text-white border-none px-5 py-2.5 rounded-[7px] text-[13.5px] font-medium font-sans cursor-pointer transition-colors"
          >
            Try again
          </button>
          <Link
            href="/dashboard"
            className="bg-transparent border border-nexus-accent/35 text-nexus-accent px-5 py-2.5 rounded-[7px] text-[13.5px] font-medium no-underline hover:bg-nexus-accent/5 transition-colors"
          >
            Go to Dashboard
          </Link>
        </div>
      </div>
    </div>
  )
}