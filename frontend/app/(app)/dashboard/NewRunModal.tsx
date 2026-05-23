/**
 * Modal overlay for creating a new NEXUS agent orchestration run.
 *
 * Renders a full-screen backdrop with a centered card containing a textarea
 * for the user query. On submit, calls POST /api/v1/runs and invokes
 * onSuccess() so the parent can trigger SWR revalidation and navigate.
 */
'use client'

import { useState, useEffect, useRef, type KeyboardEvent } from 'react'
import { useRouter } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import type { CreateRunResponse } from '@/lib/types'

interface NewRunModalProps {
  /** Called after a run is successfully created with the new run_id. */
  onSuccess: (runId: string) => void
  /** Called when the user closes the modal without submitting. */
  onClose: () => void
}

/**
 * Full-screen modal for submitting a new agent run query.
 *
 * Closes on Escape key. Submits on Ctrl+Enter or button click.
 * Navigates to /runs/[run_id] after successful creation.
 */
export function NewRunModal({ onSuccess, onClose }: NewRunModalProps) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Focus textarea on mount
  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  // Close on Escape
  useEffect(() => {
    function handleKeyDown(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

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
      onSuccess(result.run_id)
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'detail' in err) {
        setError((err as { detail: string }).detail)
      } else {
        setError('Failed to start run. Please try again.')
      }
      setLoading(false)
    }
  }

  function handleTextareaKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ background: 'rgba(28,28,26,0.55)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* Modal card */}
      <div className="bg-white rounded-[10px] border border-black/[0.08] shadow-[0_8px_40px_rgba(0,0,0,0.18)] w-full max-w-[600px] p-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-[16px] font-semibold text-[#1C1C1A]">New run</h2>
            <p className="text-[12.5px] text-[#888780] mt-[2px]">
              Describe what you want NEXUS to research, build, or explore.
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-md text-[#888780] hover:text-[#1C1C1A] hover:bg-[#F0EFE9] transition-colors"
            aria-label="Close modal"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 bg-[#FDECEA] border border-[rgba(226,75,74,0.2)] rounded-[6px] px-3 py-2 mb-4 text-[13px] text-[#E24B4A]">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.3"/>
              <path d="M6.5 4.5v2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
              <circle cx="6.5" cy="8.5" r="0.7" fill="currentColor"/>
            </svg>
            {error}
          </div>
        )}

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleTextareaKeyDown}
          disabled={loading}
          rows={5}
          placeholder="Research the latest breakthroughs in diffusion models for video generation, summarise the top 3 papers, and write a Python snippet to load CogVideoX using the diffusers library."
          className="w-full border border-black/[0.12] rounded-[7px] px-[14px] py-3 text-[14px] text-[#1C1C1A] font-sans outline-none resize-none leading-[1.65] placeholder:text-[#B0AFA9] focus:border-[#534AB7] focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)] disabled:bg-[#F5F4F0] disabled:cursor-not-allowed transition-[border-color,box-shadow]"
        />

        {/* Footer */}
        <div className="flex items-center justify-between mt-4">
          <span className="text-[12px] text-[#B0AFA9]">
            <kbd className="bg-[#F0EFE9] border border-black/[0.12] px-[5px] py-[2px] rounded text-[11px]">Ctrl</kbd>
            {' '}+{' '}
            <kbd className="bg-[#F0EFE9] border border-black/[0.12] px-[5px] py-[2px] rounded text-[11px]">Enter</kbd>
            {' '}to submit
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              disabled={loading}
              className="bg-transparent text-[#534AB7] border-[1.5px] border-[#534AB7] px-4 py-[8px] rounded-[6px] text-[13.5px] font-medium cursor-pointer font-sans transition-colors hover:bg-[rgba(83,74,183,0.05)] disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={loading || !query.trim()}
              className="bg-[#534AB7] hover:bg-[#4840A0] disabled:bg-[#F1EFE8] disabled:text-[#B0AFA9] disabled:cursor-not-allowed text-white border-none px-4 py-[8px] rounded-[6px] text-[13.5px] font-medium cursor-pointer font-sans inline-flex items-center gap-[7px] transition-colors"
            >
              {loading ? (
                <>
                  <span className="w-[14px] h-[14px] border-2 border-white/35 border-t-white rounded-full animate-spin flex-shrink-0" />
                  Starting…
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <polygon points="2,1 11,6 2,11" fill="white"/>
                  </svg>
                  Start run
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}