// frontend/app/(app)/runs/[run_id]/ThoughtTrace.tsx
'use client'

/**
 * ThoughtTrace — renders the live event timeline for a run.
 *
 * Two modes:
 *   - Live:   run.status === 'running' → mounts useSSEStream, events arrive in real time
 *   - Static: run.status === 'completed'|'failed' → renders initialEvents from DB, no SSE
 *
 * Design reference: Page 3 and 3b in docs/design/nexus-all-pages.html.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import type { CancelRunResponse, Run, RunEvent } from '@/lib/types'
import { apiFetch } from '@/lib/api'
import { useSSEStream } from '@/hooks/useSSEStream'
import { EventCard } from './EventCard'
import { RunSummary } from './RunSummary'
import { MarkdownRenderer } from '@/components/ui/MarkdownRenderer'

interface ThoughtTraceProps {
  run: Run
  /** Pre-loaded events from DB for completed runs. Empty array for active runs. */
  initialEvents: RunEvent[]
}

/**
 * Final answer block shown after run_complete.
 */
function FinalAnswer({ output }: { output: string }) {
  return (
    <div className="bg-white rounded-[8px] border-[1.5px] border-nexus-success/20 px-[22px] py-5 mb-4">
      <div className="flex items-center gap-[7px] text-[11.5px] font-bold text-nexus-success uppercase tracking-[0.06em] mb-3">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 7l4 4L12 3" stroke="#1D9E75" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
        Your answer
      </div>
      <div className="text-[14px] text-nexus-dark leading-[1.8]">
        <MarkdownRenderer content={output} />
      </div>
    </div>
  )
}

/**
 * ThoughtTrace renders the complete live or historical event timeline.
 */
export function ThoughtTrace({ run, initialEvents }: ThoughtTraceProps) {
  const isLive = run.status === 'running'
  const bottomRef = useRef<HTMLDivElement>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const [cancelRequested, setCancelRequested] = useState(false)

  const { events: liveEvents, status, finalOutput, error, retry } = useSSEStream(
    run.run_id,
    isLive
  )

  const displayEvents = isLive ? liveEvents : initialEvents
  const completedOutput = useMemo(() => {
    const terminalEvent = [...displayEvents]
      .reverse()
      .find((event) => event.event_type === 'run_complete')
    const terminalOutput =
      terminalEvent?.payload?.final_answer ??
      terminalEvent?.payload?.output ??
      terminalEvent?.payload?.response
    if (typeof terminalOutput === 'string' && terminalOutput.trim()) return terminalOutput

    const llmEvent = [...displayEvents]
      .reverse()
      .find((event) => event.event_type === 'llm_response' || event.event_type === 'orchestrator_synthesize')
    const llmContent = llmEvent?.payload?.content
    return typeof llmContent === 'string' && llmContent.trim() ? llmContent : null
  }, [displayEvents])

  const terminalEventType = useMemo(
    () =>
      [...displayEvents]
        .reverse()
        .find((event) =>
          event.event_type === 'run_complete' ||
          event.event_type === 'run_error' ||
          event.event_type === 'run_cancelled'
        )?.event_type,
    [displayEvents]
  )

  const derivedRunStatus =
    run.status !== 'running'
      ? run.status
      : terminalEventType === 'run_complete'
      ? 'completed'
      : terminalEventType === 'run_error'
      ? 'failed'
      : terminalEventType === 'run_cancelled'
      ? 'cancelled'
      : run.status

  // Auto-scroll to bottom as new events arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [displayEvents.length])

  const canCancel =
    (run.status === 'running' || run.status === 'pending') &&
    status !== 'closed' &&
    !cancelRequested

  async function handleCancelRun() {
    if (!canCancel || isCancelling) return

    setCancelMessage(null)
    setIsCancelling(true)

    try {
      await apiFetch<CancelRunResponse>(`/api/v1/runs/${encodeURIComponent(run.run_id)}/cancel`, {
        method: 'POST',
      })
      setCancelRequested(true)
      setCancelMessage('Run cancellation requested successfully.')
    } catch (err) {
      const message =
        err && typeof err === 'object' && 'detail' in err
          ? (err as { detail?: string }).detail ?? 'Unable to cancel run.'
          : 'Unable to cancel run.'
      setCancelMessage(message)
    } finally {
      setIsCancelling(false)
    }
  }

  return (
    <div className="grid grid-cols-[1fr_288px] gap-4 items-start">
      {/* Left: event trace */}
      <div>
        {/* Final answer (completed run or completed stream) */}
        {(finalOutput || completedOutput) && (
          <FinalAnswer output={finalOutput ?? completedOutput ?? ''} />
        )}

        {/* Error banner */}
        {error && isLive && (
          <div className="bg-[#FDECEA] border border-nexus-error/20 rounded-[8px] px-4 py-3 mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2 text-[13px] text-nexus-error">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.3"/><path d="M7 4.5v3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><circle cx="7" cy="9.5" r="0.7" fill="currentColor"/></svg>
              {error}
            </div>
            <button onClick={retry} className="text-[12px] text-nexus-error font-medium hover:underline">Retry</button>
          </div>
        )}

        {/* Event cards */}
        <div className="bg-white rounded-[8px] border border-black/[0.07] overflow-hidden">
          <div className="px-[18px] py-3 border-b border-black/[0.06] flex items-center gap-2">
            {isLive && status === 'open' && (
              <span className="w-[7px] h-[7px] bg-nexus-success rounded-full animate-pulse" />
            )}
            <span className="text-[13px] font-semibold text-nexus-dark">Thought trace</span>
            {isLive && status === 'open' && (
              <span className="text-[11.5px] text-nexus-success font-medium">streaming live</span>
            )}
          </div>

          {canCancel && (
            <div className="px-4 py-3 border-b border-black/[0.06] bg-[#FFFBF0] flex flex-col gap-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[12px] text-[#7F6D22]">
                  This run is still active. Cancel to stop further execution.
                </span>
                <button
                  type="button"
                  onClick={handleCancelRun}
                  disabled={isCancelling}
                  className="inline-flex items-center justify-center rounded-[6px] border border-[#B38A1F] bg-[#FFF6D8] px-3 py-2 text-[12.5px] font-semibold text-[#7F6D22] transition-colors hover:bg-[#F8E8A0] disabled:opacity-50"
                >
                  {isCancelling ? 'Cancelling…' : 'Cancel run'}
                </button>
              </div>
              {cancelMessage && (
                <div className="text-[12px] text-[#7F6D22]">{cancelMessage}</div>
              )}
            </div>
          )}

          {displayEvents.length === 0 ? (
            <div className="px-4 py-8 text-center text-[13px] text-nexus-muted">
              {isLive ? 'Waiting for first event…' : 'No events recorded for this run.'}
            </div>
          ) : (
            <>
              {displayEvents.map((ev, i) => (
                <EventCard key={ev.event_id ?? i} event={ev} index={i} />
              ))}
              <div ref={bottomRef} />
            </>
          )}
        </div>
      </div>

      {/* Right: summary panel */}
      <RunSummary
        run={{ ...run, status: derivedRunStatus }}
        events={displayEvents}
        connectionStatus={isLive ? status : 'closed'}
      />
    </div>
  )
}
