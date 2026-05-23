// frontend/hooks/useSSEStream.ts
'use client'

/**
 * useSSEStream — manages a live SSE connection to GET /api/v1/sse/{run_id}?token=TOKEN.
 *
 * Uses the native EventSource API. Token is passed as a query param because
 *
 * Automatically closes the connection when:
 *   - The component unmounts (useEffect cleanup)
 *   - A terminal event (run_complete, run_error) is received
 *
 * @param runId - UUID of the run to stream events for.
 * @param enabled - Set to false to skip connection (e.g. run already completed).
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { getToken } from '@/lib/auth'
import type { EventType, RunEvent } from '@/lib/types'

export type SSEConnectionStatus = 'connecting' | 'open' | 'error' | 'closed'

export interface UseSSEStreamResult {
  events: RunEvent[]
  status: SSEConnectionStatus
  finalOutput: string | null
  error: string | null
  retry: () => void
}

const TERMINAL_EVENT_TYPES = new Set(['run_complete', 'run_error'])
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080'
const SSE_EVENT_TYPES = [
  'thought',
  'tool_call',
  'tool_result',
  'agent_start',
  'agent_end',
  'orchestrator_plan',
  'orchestrator_dispatch',
  'orchestrator_synthesize',
  'run_start',
  'run_complete',
  'run_error',
  'memory_read',
  'memory_write',
  'llm_response',
  'code_iteration',
  'error',
]

interface RawSSEEvent {
  event_id?: string
  run_id?: string
  task_id?: string | null
  event_type?: string
  source?: string
  agent_name?: string
  payload?: Record<string, unknown>
  created_at?: string
  timestamp?: number
}

function normalizeSSEEvent(raw: RawSSEEvent, runId: string): RunEvent {
  const timestamp =
    typeof raw.timestamp === 'number'
      ? new Date(raw.timestamp * 1000).toISOString()
      : undefined

  const createdAt = raw.created_at ?? timestamp ?? new Date().toISOString()
  const eventType = raw.event_type ?? 'thought'

  return {
    event_id: raw.event_id ?? `${runId}:${eventType}:${createdAt}`,
    run_id: raw.run_id ?? runId,
    task_id: raw.task_id ?? null,
    event_type: eventType as EventType,
    source: raw.source ?? raw.agent_name ?? 'unknown',
    payload: raw.payload ?? {},
    created_at: createdAt,
  }
}

export function useSSEStream(
  runId: string,
  enabled: boolean = true
): UseSSEStreamResult {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [status, setStatus] = useState<SSEConnectionStatus>('connecting')
  const [finalOutput, setFinalOutput] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)

  const esRef = useRef<EventSource | null>(null)

  const retry = useCallback(() => {
    setEvents([])
    setStatus('connecting')
    setFinalOutput(null)
    setError(null)
    setRetryKey((k) => k + 1)
  }, [])

  useEffect(() => {
    if (!enabled || !runId) return

    const token = getToken()
    if (!token) {
      setStatus('error')
      setError('Not authenticated')
      return
    }

    const url = `${BASE_URL}/api/v1/sse/${encodeURIComponent(runId)}?token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => {
      setStatus('open')
      setError(null)
    }

    const handleEvent = (event: MessageEvent<string>) => {
      try {
        const parsed = normalizeSSEEvent(JSON.parse(event.data) as RawSSEEvent, runId)
        setEvents((prev) => [...prev, parsed])

        if (TERMINAL_EVENT_TYPES.has(parsed.event_type)) {
          if (parsed.event_type === 'run_complete') {
            const output = (parsed.payload as Record<string, unknown>)?.output as string | undefined
            setFinalOutput(output ?? null)
          }
          if (parsed.event_type === 'run_error') {
            const errMsg = (parsed.payload as Record<string, unknown>)?.error as string | undefined
            setError(errMsg ?? 'Run failed')
          }
          setStatus('closed')
          es.close()
        }
      } catch {
        // Non-JSON chunk (keepalive comment, stream-open line) — ignore
      }
    }

    es.onmessage = handleEvent
    for (const eventType of SSE_EVENT_TYPES) {
      es.addEventListener(eventType, handleEvent)
    }

    es.onerror = () => {
      setStatus('error')
      setError('Connection lost. The run may still be in progress.')
      es.close()
    }

    return () => {
      for (const eventType of SSE_EVENT_TYPES) {
        es.removeEventListener(eventType, handleEvent)
      }
      es.close()
      esRef.current = null
    }
  }, [runId, enabled, retryKey])

  return { events, status, finalOutput, error, retry }
}
