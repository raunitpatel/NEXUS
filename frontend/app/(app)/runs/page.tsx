// frontend/app/(app)/runs/page.tsx

import { TopBar } from '@/components/ui/TopBar'

export default function RunsPage() {
  return (
    <>
      <TopBar title="Runs" />

      <div className="flex-1 bg-nexus-bg overflow-y-auto p-6">
        <div className="bg-white border border-black/[0.07] rounded-[8px] px-8 py-14 text-center">
          <div className="w-12 h-12 rounded-[10px] bg-[#F0EFE9] flex items-center justify-center mx-auto mb-4">
            <svg
              width="22"
              height="22"
              viewBox="0 0 16 16"
              fill="none"
              className="text-nexus-muted"
            >
              <circle
                cx="8"
                cy="8"
                r="6"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <polyline
                points="8,5 8,8 10,10"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </div>

          <h1 className="text-[18px] font-semibold text-nexus-dark mb-2">
            No run selected
          </h1>

          <p className="text-[13.5px] text-nexus-muted leading-[1.7] max-w-[420px] mx-auto">
            Select a run from Dashboard or History to inspect the complete
            orchestrator trace, events, agent activity, and final output.
          </p>
        </div>
      </div>
    </>
  )
}