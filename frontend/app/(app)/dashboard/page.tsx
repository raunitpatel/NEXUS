/**
 * Dashboard page — authenticated home screen for NEXUS.
 *
 * Displays user activity metrics, active runs, and the 10 most recent runs.
 * Polling via useRuns (5s interval) keeps status badges live without SSE.
 * "New Run" button opens NewRunModal which POSTs to /api/v1/runs.
 *
 * Design reference: docs/design/nexus-all-pages.html — Page 2 Dashboard
 */
'use client'

import { useState, useCallback, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { TopBar } from '@/components/ui/TopBar'
import { RunCard } from '@/components/runs/RunCard'
import { StatusBadge } from '@/components/runs/StatusBadge'
import { AgentsUsedBadge } from '@/components/runs/AgentsUsedBadge'
import { NewRunModal } from './NewRunModal'
import { useRuns } from '@/hooks/useRun'
import type { Run } from '@/lib/types'


export default function DashboardPage() {
  const router = useRouter()
  const [showModal, setShowModal] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const { runs, isLoading, isError, mutate } = useRuns({ limit: 10 })

  const activeRuns = runs.filter((r) => r.status === 'running')
  const completedRuns = runs.filter((r) => r.status === 'completed')
  const failedRuns = runs.filter((r) => r.status === 'failed')
  const successRate =
    runs.length > 0
      ? Math.round((completedRuns.length / runs.length) * 100)
      : 0

  const handleRunSuccess = useCallback(
    (runId: string) => {
      setShowModal(false)
      mutate()
      router.push(`/runs/${runId}`)
    },
    [mutate, router]
  )

  useEffect(() => {
    if (activeRuns.length === 0) return

    const intervalId = window.setInterval(() => {
      setNow(Date.now())
    }, 1000)

    return () => window.clearInterval(intervalId)
  }, [activeRuns.length])

  return (
    <>
      <TopBar title="Dashboard" />

      <div className="flex-1 bg-nexus-bg overflow-y-auto p-6">

        {/* Page heading row */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-[16px] font-semibold text-nexus-dark">
              Your activity overview
            </h2>
            <p className="text-[12.5px] text-nexus-muted mt-[2px]">
              All data shown is yours only — filtered by your account
            </p>
          </div>

          <button
            onClick={() => setShowModal(true)}
            className="bg-nexus-accent hover:bg-nexus-accent-hover text-white border-none px-[14px] py-[8px] rounded-[6px] text-[13px] font-medium font-sans inline-flex items-center gap-[6px] transition-colors cursor-pointer"
          >
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
              <polygon points="2,1 10,5.5 2,10" fill="white" />
            </svg>
            New run
          </button>
        </div>

        {/* Metric cards */}
        <div className="grid grid-cols-4 gap-3 mb-[22px]">
          <MetricCard
            label="My total runs"
            value={String(runs.length)}
            sub={isLoading ? 'Loading…' : undefined}
          />
          <MetricCard
            label="Running now"
            value={String(activeRuns.length)}
            live={activeRuns.length > 0}
            sub={activeRuns.length > 0 ? `${activeRuns.length} agent${activeRuns.length > 1 ? 's' : ''} active` : 'All idle'}
          />
          <MetricCard
            label="My success rate"
            value={`${successRate}%`}
            sub={`${completedRuns.length} completed`}
          />
          <MetricCard
            label="Failed"
            value={String(failedRuns.length)}
            sub="in current view"
            valueColor={failedRuns.length > 0 ? 'text-nexus-error' : undefined}
          />
        </div>

        {/* Active runs panel */}
        {activeRuns.length > 0 && (
          <div className="bg-white rounded-[8px] border border-black/[0.07] mb-[18px]">
            <div className="px-[18px] py-[12px] border-b border-black/[0.06] flex items-center gap-2">
              <span className="w-[7px] h-[7px] rounded-full bg-nexus-success animate-pulse" />
              <span className="text-[13px] font-semibold text-nexus-dark">
                Running now
              </span>
            </div>
            {activeRuns.map((run) => (
              <ActiveRunRow key={run.run_id} run={run} now={now} />
            ))}
          </div>
        )}

        {/* Recent runs table */}
        <div className="bg-white rounded-[8px] border border-black/[0.07]">
          <div className="px-[18px] py-[12px] border-b border-black/[0.06] flex items-center justify-between">
            <span className="text-[13px] font-semibold text-nexus-dark">
              My recent runs
            </span>
            <Link
              href="/history"
              className="text-[12.5px] text-nexus-accent font-medium no-underline hover:underline"
            >
              View all history →
            </Link>
          </div>

          {isLoading && runs.length === 0 ? (
            <RunsTableSkeleton />
          ) : isError ? (
            <div className="px-[18px] py-6 text-[13px] text-nexus-error">
              Failed to load runs. Please refresh.
            </div>
          ) : runs.length === 0 ? (
            <EmptyRunsState onNewRun={() => setShowModal(true)} />
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {['Run ID', 'query', 'Agent', 'Status', 'Duration', 'Started', ''].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-[11.5px] font-semibold text-nexus-muted uppercase tracking-[0.05em] px-[14px] py-[10px] text-left border-b border-black/[0.07]"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <RunCard key={run.run_id} run={run} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* New Run Modal */}
      {showModal && (
        <NewRunModal
          onSuccess={handleRunSuccess}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface MetricCardProps {
  label: string
  value: string
  sub?: string
  live?: boolean
  valueColor?: string
}

function MetricCard({ label, value, sub, live, valueColor }: MetricCardProps) {
  return (
    <div className="bg-white rounded-[8px] border border-black/[0.07] px-[18px] py-[16px]">
      <div className="text-[12px] text-nexus-muted font-medium mb-2">{label}</div>
      <div
        className={`text-[28px] font-medium leading-none mb-2 flex items-center gap-[9px] ${valueColor ?? 'text-nexus-dark'}`}
      >
        {value}
        {live && (
          <span className="w-[7px] h-[7px] rounded-full bg-nexus-success animate-pulse" />
        )}
      </div>
      {sub && <div className="text-[11.5px] text-nexus-muted">{sub}</div>}
    </div>
  )
}

interface ActiveRunRowProps {
  run: Run
  now: number
}

function getElapsedSeconds(run: Run, now: number): number {
  if (typeof run.duration_seconds === 'number') {
    return Math.max(0, Math.floor(run.duration_seconds))
  }

  const startedAt = new Date(run.created_at).getTime()
  if (!Number.isFinite(startedAt)) return 0

  return Math.max(0, Math.floor((now - startedAt) / 1000))
}

function formatRunningTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`

  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (mins < 60) return `${mins}m ${secs}s`

  const hrs = Math.floor(mins / 60)
  const remainingMins = mins % 60
  return `${hrs}h ${remainingMins}m`
}

function getRunningProgress(seconds: number): number {
  if (seconds <= 0) return 8

  return Math.min(95, Math.max(8, Math.round((seconds / (seconds + 15)) * 100)))
}

function ActiveRunRow({ run, now }: ActiveRunRowProps) {
  const elapsedSeconds = getElapsedSeconds(run, now)
  const progress = getRunningProgress(elapsedSeconds)

  return (
    <div className="px-[18px] py-[13px] border-b border-black/[0.05] last:border-b-0">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-[10px] mb-[3px]">
            <span className="font-mono text-[12px] text-nexus-accent">
              {run.run_id.slice(0, 10)}
            </span>
          </div>
          <div className="text-[13px] text-nexus-body overflow-hidden text-ellipsis whitespace-nowrap max-w-[500px]">
            {run.query.length > 80 ? run.query.slice(0, 80) + '…' : run.query}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <StatusBadge status={run.status} />
          <Link
            href={`/runs/${run.run_id}`}
            className="bg-transparent text-nexus-accent border border-nexus-accent/35 px-[11px] py-[5px] rounded-[5px] text-[12px] font-medium no-underline hover:bg-nexus-accent/[0.05] transition-colors whitespace-nowrap"
          >
            Watch live →
          </Link>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-[6px] min-w-0">
          <AgentsUsedBadge agents={run.agents_used} />
          <span className="text-[11.5px] text-nexus-muted ml-1 whitespace-nowrap">
            running for {formatRunningTime(elapsedSeconds)}
          </span>
        </div>

        <div
          className="w-[120px] h-[3px] bg-black/[0.04] rounded-[2px] overflow-hidden flex-shrink-0"
          aria-label={`Run progress ${progress}%`}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div
            className="h-full bg-nexus-accent rounded-[2px] animate-pulse transition-[width] duration-700 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  )
}

function RunsTableSkeleton() {
  return (
    <div className="p-4 space-y-3">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className="h-[40px] bg-black/[0.04] rounded-[4px] animate-pulse"
          style={{ backgroundSize: '400px 100%' }}
        />
      ))}
    </div>
  )
}

interface EmptyRunsStateProps {
  onNewRun: () => void
}

function EmptyRunsState({ onNewRun }: EmptyRunsStateProps) {
  return (
    <div className="flex flex-col items-center text-center px-6 py-10">
      <div className="w-12 h-12 bg-black/[0.04] text-nexus-muted rounded-[11px] flex items-center justify-center mb-[14px]">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
          <polygon points="10,8 17,12 10,16" fill="currentColor" />
        </svg>
      </div>
      <div className="text-[14px] font-semibold text-nexus-dark mb-[6px]">
        No runs yet
      </div>
      <div className="text-[12.5px] text-nexus-muted leading-[1.55] mb-[18px]">
        Start your first agent run using the New Run button above.
      </div>
      <button
        onClick={onNewRun}
        className="bg-nexus-accent hover:bg-nexus-accent-hover text-white border-none px-[14px] py-[7px] rounded-[6px] text-[12.5px] font-medium font-sans inline-flex items-center gap-[6px] transition-colors cursor-pointer"
      >
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
          <path d="M5.5 1v9M1 5.5h9" stroke="white" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
        New Run
      </button>
    </div>
  )
}
