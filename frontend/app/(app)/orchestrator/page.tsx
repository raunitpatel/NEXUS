// frontend/app/(app)/orchestrator/page.tsx
'use client'

import { useState, KeyboardEvent, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { TopBar } from '@/components/ui/TopBar'
import { apiFetch } from '@/lib/api'
import type { CreateRunResponse, ApiError } from '@/lib/types'
import { getToken, subscribeTokenChange } from '@/lib/auth'

interface RecentQuery {
  query: string
  timestamp: string
  run_id: string
}

function timeAgo(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  if (hours < 24) return `Today ${new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  return 'Yesterday'
}

export default function OrchestratorPage() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  // Orchestrator chooses agents automatically — no toggles in the UI
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [recentQueries, setRecentQueries] = useState<RecentQuery[]>([])

  // Load recent runs from localStorage for display
  useEffect(() => {
    const decodePayload = (token?: string | null) => {
      try {
        if (!token) return null
        const parts = token.split('.')
        if (parts.length !== 3) return null
        const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
        return JSON.parse(atob(payload)) as Record<string, any>
      } catch {
        return null
      }
    }

    const loadForCurrentUser = (token?: string | null) => {
      try {
        const payload = decodePayload(token ?? getToken())
        const userId = payload?.sub ?? 'anon'
        const key = `nexus_recent_queries_${userId}`
        const stored = localStorage.getItem(key)
        if (stored) setRecentQueries(JSON.parse(stored))
        else setRecentQueries([])
      } catch {
        // ignore
      }
    }

    // initial load
    loadForCurrentUser()

    // reload when token changes (user login/logout)
    const unsubscribe = subscribeTokenChange(() => loadForCurrentUser())
    return unsubscribe
  }, [])

  // No toggleAgent; orchestrator will dispatch agents server-side.

  async function handleSubmit() {
    const q = query.trim()
    if (!q || loading) return
    setError('')
    setLoading(true)
    try {
      const result = await apiFetch<CreateRunResponse>('/api/v1/runs', {
        method: 'POST',
        body: { query: q },
      })
      // Save to recent queries
      const newEntry: RecentQuery = { query: q, timestamp: new Date().toISOString(), run_id: result.run_id }
      const updated = [newEntry, ...recentQueries].slice(0, 10)
      setRecentQueries(updated)
      try {
        const token = getToken()
        const payload = token
          ? (() => { try { const p = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'); return JSON.parse(atob(p)) as Record<string, any> } catch { return null } })()
          : null
        const userId = payload?.sub ?? 'anon'
        const key = `nexus_recent_queries_${userId}`
        localStorage.setItem(key, JSON.stringify(updated))
      } catch {
        // ignore storage errors
      }
      // Navigate to live run view
      router.push(`/runs/${result.run_id}`)
    } catch (err: unknown) {
      // apiFetch throws an object of shape ApiError for non-2xx responses.
      if (err && typeof err === 'object' && 'detail' in err) {
        setError((err as ApiError).detail)
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Failed to start run. Please try again.')
      }
      setLoading(false)
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }

  function fillQuery(q: string) {
    setQuery(q)
  }

  return (
    <>
      <TopBar title="Orchestrator" />
      <div className="flex-1 bg-nexus-bg overflow-y-auto p-6">

        {/* Greeting */}
        <div className="mb-5">
          <h2 className="text-[20px] font-semibold text-nexus-dark mb-1">Good day 👋</h2>
          <p className="text-[13.5px] text-nexus-muted">What do you want to research, build, or explore today?</p>
        </div>

        {/* Query box — hero */}
        <div className="bg-white rounded-[10px] border-[1.5px] border-nexus-accent/[0.22] shadow-[0_2px_14px_rgba(83,74,183,0.08)] p-5 mb-4">
          <p className="text-[11px] font-bold text-nexus-muted uppercase tracking-[0.08em] mb-[10px]">Your query</p>

          {error && (
            <div className="text-[13px] text-nexus-error mb-3 flex items-center gap-2">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.3"/><path d="M6.5 4.5v2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><circle cx="6.5" cy="8.5" r="0.7" fill="currentColor"/></svg>
              {error}
            </div>
          )}

          <textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={4}
            disabled={loading}
            placeholder="Research the latest breakthroughs in diffusion models for video generation, summarise the top 3 papers, and write a Python snippet to load CogVideoX using the diffusers library."
            className="w-full border border-black/[0.12] rounded-[7px] px-[14px] py-3 text-[14px] text-nexus-dark font-sans outline-none resize-none leading-[1.65] placeholder:text-nexus-subtle focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)] disabled:bg-[#F5F4F0] disabled:cursor-not-allowed transition-[border-color,box-shadow]"
          />

          <div className="flex items-end justify-between mt-[14px] gap-4">
                    {/* Orchestrator will pick agents automatically; no toggles shown */}

            {/* Submit */}
            <button
              type="button"
              onClick={handleSubmit}
              disabled={loading || !query.trim()}
              className="bg-nexus-accent hover:bg-nexus-accent-hover disabled:bg-nexus-subtle disabled:cursor-not-allowed text-white border-none px-[22px] py-[10px] rounded-[7px] text-[13.5px] font-medium font-sans inline-flex items-center gap-[7px] transition-colors whitespace-nowrap flex-shrink-0"
            >
              {loading ? (
                <>
                  <span className="w-[14px] h-[14px] border-2 border-white/35 border-t-white rounded-full animate-spin" />
                  Starting…
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="2,1 11,6 2,11" fill="white"/></svg>
                  Start run
                </>
              )}
            </button>
          </div>
        </div>

        {/* Keyboard hint */}
        <div className="text-[12px] text-nexus-subtle mb-6 flex items-center gap-4">
          <span>
            <kbd className="bg-[#F0EFE9] border border-black/[0.12] px-[6px] py-[2px] rounded text-[11px]">Ctrl</kbd>
            {' '}+{' '}
            <kbd className="bg-[#F0EFE9] border border-black/[0.12] px-[6px] py-[2px] rounded text-[11px]">Enter</kbd>
            {' '}to submit
          </span>
        </div>

        {/* Recent queries */}
        {recentQueries.length > 0 && (
          <div>
            <p className="text-[11px] font-bold text-nexus-muted uppercase tracking-[0.08em] mb-[10px]">Your recent queries</p>
            <div className="flex flex-col gap-[6px]">
              {recentQueries.map((item, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => fillQuery(item.query)}
                  className="bg-white border border-black/[0.07] rounded-[7px] px-[14px] py-[10px] flex items-center gap-3 cursor-pointer text-left transition-[border-color] hover:border-nexus-accent/[0.2] w-full"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-nexus-subtle flex-shrink-0">
                    <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
                    <path d="M9.5 9.5l2.5 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                  </svg>
                  <span className="text-[13px] text-nexus-body flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{item.query}</span>
                  <span className="text-[11.5px] text-nexus-subtle flex-shrink-0">{timeAgo(item.timestamp)}</span>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="text-nexus-subtle flex-shrink-0">
                    <path d="M2 6h8M7 3l3 3-3 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Empty state if no recent queries */}
        {recentQueries.length === 0 && (
          <div>
            <p className="text-[11px] font-bold text-nexus-muted uppercase tracking-[0.08em] mb-[10px]">Suggested queries</p>
            <div className="flex flex-col gap-[6px]">
              {[
                'Summarize the top 5 AI research labs by publication count in 2024',
                'Generate a typed REST API client in Python for the GitHub API',
                'What is the current weather in Tokyo and should I bring an umbrella next week?',
              ].map((suggestion, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => fillQuery(suggestion)}
                  className="bg-white border border-black/[0.07] rounded-[7px] px-[14px] py-[10px] flex items-center gap-3 cursor-pointer text-left hover:border-nexus-accent/[0.2] transition-[border-color] w-full"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-nexus-subtle flex-shrink-0">
                    <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
                    <path d="M9.5 9.5l2.5 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                  </svg>
                  <span className="text-[13px] text-nexus-body flex-1">{suggestion}</span>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="text-nexus-subtle flex-shrink-0">
                    <path d="M2 6h8M7 3l3 3-3 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}