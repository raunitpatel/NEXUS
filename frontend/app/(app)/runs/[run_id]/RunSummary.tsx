// frontend/app/(app)/runs/[run_id]/RunSummary.tsx
'use client'

/**
 * RunSummary — sticky right-panel showing run metadata and live progress.
 * Matches the sum-panel / sum-sec CSS classes from docs/design/nexus-all-pages.html.
 */

import type { Run, RunEvent } from '@/lib/types'
import type { SSEConnectionStatus } from '@/hooks/useSSEStream'
import clsx from 'clsx'

interface RunSummaryProps {
  run: Run
  events: RunEvent[]
  connectionStatus: SSEConnectionStatus
}

interface AgentUsage {
  [agentType: string]: { dispatched: number; done: number }
}

const AGENT_CHIP_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  search:       { bg: '#E6F1FB', text: '#0C447C', dot: '#378ADD' },
  code:         { bg: '#FAEEDA', text: '#633806', dot: '#EF9F27' },
  memory_read:  { bg: '#EEEDFE', text: '#3C3489', dot: '#7F77DD' },
  memory_write: { bg: '#EEEDFE', text: '#3C3489', dot: '#7F77DD' },
  tool:         { bg: '#E1F5EE', text: '#085041', dot: '#1D9E75' },
}

/**
 * Sticky summary panel for the run detail page.
 */
export function RunSummary({ run, events, connectionStatus }: RunSummaryProps) {
  // Derive agent usage from events
  const agentUsage: AgentUsage = {}
  for (const ev of events) {
    if (ev.event_type === 'orchestrator_dispatch') {
      const agentType = (ev.payload as Record<string, unknown>)?.agent_type as string | undefined
      if (agentType) {
        agentUsage[agentType] = agentUsage[agentType] ?? { dispatched: 0, done: 0 }
        agentUsage[agentType].dispatched++
      }
    }
    if (ev.event_type === 'tool_result') {
      const agentType = (ev.payload as Record<string, unknown>)?.agent_type as string | undefined
      if (agentType) {
        agentUsage[agentType] = agentUsage[agentType] ?? { dispatched: 0, done: 0 }
        agentUsage[agentType].done++
      }
    }
  }

  const connectionLabel = {
    connecting: 'Connecting…',
    open: 'Streaming live',
    error: 'Connection error',
    closed: 'Stream closed',
  }[connectionStatus]

  return (
    <div className="sticky top-0 flex flex-col gap-3">
      {/* Agent status card */}
      {Object.keys(agentUsage).length > 0 && (
        <div className="bg-white rounded-[8px] border border-black/[0.07] overflow-hidden">
          <div className="px-4 py-3 border-b border-black/[0.06]">
            <span className="text-[13px] font-semibold text-nexus-dark">Agent status</span>
          </div>
          {Object.entries(agentUsage).map(([agentType, usage]) => {
            const style = AGENT_CHIP_STYLES[agentType] ?? AGENT_CHIP_STYLES.tool
            const done = usage.done >= usage.dispatched
            return (
              <div key={agentType} className="flex items-center gap-2 px-[14px] py-[10px] border-b border-black/[0.05] last:border-b-0">
                <span
                  className="inline-flex items-center gap-1 px-[7px] py-[2px] rounded-[4px] text-[11px] font-semibold w-[72px] justify-center"
                  style={{ background: style.bg, color: style.text }}
                >
                  <span className="w-[5px] h-[5px] rounded-full" style={{ background: style.dot }} />
                  {agentType.replace('_', ' ')}
                </span>
                {done ? (
                  <span className="text-[12px] text-nexus-success font-medium flex items-center gap-1">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                    Done
                  </span>
                ) : (
                  <span className="text-[12px] text-nexus-muted font-medium">In progress…</span>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Progress card */}
      <div className="bg-white rounded-[8px] border border-black/[0.07] overflow-hidden">
        <div className="px-4 py-3 border-b border-black/[0.06]">
          <span className="text-[13px] font-semibold text-nexus-dark">Progress</span>
        </div>
        <div className="px-4 py-3 border-b border-black/[0.06]">
          <div className="text-[11px] font-bold text-nexus-muted uppercase tracking-[0.06em] mb-2">Events</div>
          <div className="flex justify-between text-[12.5px]">
            <span className="text-nexus-muted">Total</span>
            <span className="font-semibold text-nexus-dark">{events.length}</span>
          </div>
        </div>
        <div className="px-4 py-3 border-b border-black/[0.06]">
          <div className="text-[11px] font-bold text-nexus-muted uppercase tracking-[0.06em] mb-2">Stream</div>
          <span className={clsx(
            'text-[12px] font-medium',
            connectionStatus === 'open' ? 'text-nexus-success' : connectionStatus === 'error' ? 'text-nexus-error' : 'text-nexus-muted'
          )}>
            {connectionLabel}
          </span>
        </div>
        <div className="px-4 py-3">
          <div className="text-[11px] font-bold text-nexus-muted uppercase tracking-[0.06em] mb-1">Run ID</div>
          <div className="font-mono text-[12px] text-nexus-accent">{run.run_id.slice(0, 12)}…</div>
        </div>
      </div>
    </div>
  )
}