/**
 * Shared TypeScript interfaces for NEXUS frontend.
 *
 * All API response shapes are defined here. Import from '@/lib/types'
 * — never define inline interfaces in components or hooks.
 */

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  display_name?: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface RegisterResponse {
  user_id: string
  email: string
  display_name: string | null
}

// ── Runs ──────────────────────────────────────────────────────────────────────

export type RunStatus = | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
export type AgentUsed = | 'Search Agent' | 'Code Agent' | 'Memory Agent' | 'Tool Agent'

export interface Run {
  run_id: string
  status: RunStatus
  query: string
  created_at: string
  duration_seconds?: number | null
  agents_used?: AgentUsed[]
  input_tokens?: number
  output_tokens?: number
  total_tokens?: number
  latency_ms?: number | null
}

export interface RunListResponse {
  runs: Run[]
  total_count: number
  page: number
  size: number
}

export interface CreateRunRequest {
  query: string
}

export interface CreateRunResponse {
  run_id: string
  status: RunStatus
}

// ── Agents ────────────────────────────────────────────────────────────────────

export type AgentType = 'search' | 'code' | 'memory' | 'tool' | 'orchestrator'

export interface Agent {
  agent_id: string
  name: string
  type: AgentType
  base_url: string
  description: string | null
  is_active: boolean
  is_healthy: boolean | null
}

// ── Events (SSE) ──────────────────────────────────────────────────────────────

export type EventType =
  | 'thought'
  | 'tool_call'
  | 'tool_result'
  | 'agent_start'
  | 'agent_end'
  | 'orchestrator_plan'
  | 'orchestrator_dispatch'
  | 'orchestrator_synthesize'
  | 'run_start'
  | 'run_complete'
  | 'run_error'
  | 'memory_read'
  | 'memory_write'
  | 'llm_response'
  | 'code_iteration'

export interface RunEvent {
  event_id: string
  run_id: string
  task_id: string | null
  event_type: EventType
  source: string
  payload: Record<string, unknown>
  created_at: string
}

export interface RunDetail extends Run {
  output: string | null
  error: string | null
  metadata: Record<string, unknown>
  completed_at: string | null
}

// ── Memory ────────────────────────────────────────────────────────────────────

export interface MemorySearchResult {
  embedding_id: string
  run_id: string
  content: string
  similarity: number
  model: string
  created_at: string
}

export interface MemorySearchResponse {
  query: string
  results: MemorySearchResult[]
  from_cache: boolean
  duration_ms: number
}

// ── Metrics ───────────────────────────────────────────────────────────────────

export interface MetricsSummary {
  total_runs: number
  successful_runs: number
  failed_runs: number
  success_rate: number
  total_input_tokens: number
  total_output_tokens: number
  avg_run_duration_ms: number
  active_runs: number
  period_days: number
}

export interface AgentStat {
  agent_type: AgentType
  total_tasks: number
  successful_tasks: number
  failed_tasks: number
  success_rate: number
  avg_duration_ms: number
}

export interface DailyTokenUsage {
  date: string
  input_tokens: number
  output_tokens: number
  run_count: number
}

export interface DailyLatency {
  date: string
  avg_duration_ms: number
  p95_duration_ms: number
  run_count: number
}

// ── API errors ────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string
  status: number
}
