/**
 * Colour-coded badge group for agents used in a run.
 *
 * Matches the visual language of StatusBadge while allowing
 * multiple agents to be rendered together.
 */

import type { ReactNode } from 'react'
import type { AgentUsed } from '@/lib/types'

interface AgentsUsedBadgeProps {
  /** Agents involved in the run execution. */
  agents?: AgentUsed[]
}

const CONFIG: Record<
  AgentUsed,
  {
    bg: string
    text: string
    icon: ReactNode
  }
> = {
  'Search Agent': {
    bg: 'bg-[#EAF3FF]',
    text: 'text-[#2F6FED]',
    icon: (
      <span className="w-[6px] h-[6px] rounded-full bg-[#2F6FED] flex-shrink-0" />
    ),
  },

  'Code Agent': {
    bg: 'bg-[#F3ECFF]',
    text: 'text-[#7A4DFF]',
    icon: (
      <span className="w-[6px] h-[6px] rounded-full bg-[#7A4DFF] flex-shrink-0" />
    ),
  },

  'Memory Agent': {
    bg: 'bg-[#E8F8F2]',
    text: 'text-[#1D9E75]',
    icon: (
      <span className="w-[6px] h-[6px] rounded-full bg-[#1D9E75] flex-shrink-0" />
    ),
  },

  'Tool Agent': {
    bg: 'bg-[#FEF3E2]',
    text: 'text-[#BA7517]',
    icon: (
      <span className="w-[6px] h-[6px] rounded-full bg-[#BA7517] flex-shrink-0" />
    ),
  },
}

/**
 * Renders colour-coded agent pills.
 */
export function AgentsUsedBadge({
  agents = [],
}: AgentsUsedBadgeProps) {
  if (agents.length === 0) {
    return (
      <span className="text-[12px] text-[#888780]">
        —
      </span>
    )
  }

  return (
    <div className="flex flex-wrap gap-[6px]">
      {agents.map((agent) => {
        const { bg, text, icon } = CONFIG[agent]

        return (
          <span
            key={agent}
            className={`inline-flex items-center gap-[5px] px-[10px] py-[3px] rounded-[4px] text-[12px] font-semibold whitespace-nowrap ${bg} ${text}`}
          >
            {icon}
            {agent.replace(' Agent', '')}
          </span>
        )
      })}
    </div>
  )
}