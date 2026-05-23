// frontend/app/(app)/runs/[run_id]/page.tsx

/**
 * Run detail page — server component.
 *
 * Fetches run metadata from GET /api/v1/runs/{run_id} server-side.
 * For completed/failed runs, also fetches events from GET /api/v1/runs/{run_id}/events.
 * Passes data to ThoughtTrace client component.
 */

import { cookies } from 'next/headers'
import { notFound, redirect } from 'next/navigation'
import Link from 'next/link'
import { TopBar } from '@/components/ui/TopBar'
import { ThoughtTrace } from './ThoughtTrace'
import type { Run, RunEvent, RunStatus } from '@/lib/types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080'

async function fetchRun(runId: string, token: string): Promise<Run | null> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}/api/v1/runs/${encodeURIComponent(runId)}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
  } catch {
    return null
  }

  if (res.status === 404) return null
  if (res.status === 401) redirect('/login?reason=expired')
  if (!res.ok) return null
  return res.json() as Promise<Run>
}

async function fetchEvents(runId: string, token: string): Promise<RunEvent[]> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}/api/v1/runs/${encodeURIComponent(runId)}/events`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
  } catch {
    return []
  }

  if (res.status === 404) return []
  if (res.status === 401) redirect('/login?reason=expired')
  if (!res.ok) return []
  return res.json() as Promise<RunEvent[]>
}

const STATUS_BADGE: Record<RunStatus, { label: string; bg: string; text: string }> = {
  running:   { label: 'Running',   bg: '#E8F8F2', text: '#1D9E75' },
  completed: { label: 'Completed', bg: '#E8F8F2', text: '#1D9E75' },
  failed:    { label: 'Failed',    bg: '#FDECEA', text: '#E24B4A' },
  pending:   { label: 'Pending',   bg: '#FEF3E2', text: '#BA7517' },
  cancelled: { label: 'Cancelled', bg: '#F1EFE8', text: '#888780' },
}

interface RunDetailPageProps {
  params: { run_id: string }
}

/**
 * Run detail server page — fetches run and events, renders ThoughtTrace.
 */
export default async function RunDetailPage({ params }: RunDetailPageProps) {
  const { run_id } = params

  // Read token from cookie (set by auth.ts setToken)
  const cookieStore = cookies()
  const token = cookieStore.get('nexus_token')?.value

  if (!token) {
    redirect('/login?reason=unauthenticated')
  }

  const run = await fetchRun(run_id, token)
  if (!run) notFound()

  // For completed/failed runs, pre-load events
  const initialEvents = (run.status === 'completed' || run.status === 'failed')
    ? await fetchEvents(run_id, token)
    : []

  const badge = STATUS_BADGE[run.status]

  return (
    <>
      <TopBar title="Run detail" />
      <div className="flex-1 bg-nexus-bg overflow-y-auto p-6">

        {/* Back link */}
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-[5px] text-[12.5px] text-nexus-muted font-medium no-underline mb-[10px] hover:text-nexus-accent transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          My dashboard
        </Link>

        {/* Run header */}
        <div className="flex items-start justify-between gap-3 mb-[10px]">
          <div>
            <span className="font-mono text-[13px] text-nexus-accent">{run.run_id}</span>
            <div className="text-[15px] font-medium text-nexus-dark mt-1 mb-[10px] leading-[1.45] max-w-[580px]">
              {run.query}
            </div>
          </div>
          <span
            className="inline-flex items-center gap-[5px] px-[8px] py-[2px] rounded-[4px] text-[11.5px] font-semibold flex-shrink-0"
            style={{ background: badge.bg, color: badge.text }}
          >
            {run.status === 'running' && (
              <span className="w-[6px] h-[6px] rounded-full animate-pulse" style={{ background: badge.text }} />
            )}
            {badge.label}
          </span>
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-2 mb-[18px]">
          <span className="text-[12px] text-nexus-muted">
            Started {new Date(run.created_at).toLocaleString()}
          </span>
        </div>

        {/* ThoughtTrace — client component */}
        <ThoughtTrace run={run} initialEvents={initialEvents} />
      </div>
    </>
  )
}
