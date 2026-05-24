'use client'

/**
 * SearchBar — controlled search input for the Memory Explorer.
 *
 * Maintains raw input state internally. Calls onDebouncedChange
 * after a 300ms debounce. Design matches docs/design/nexus-all-pages.html Page 5.
 */

import { useEffect, useState } from 'react'
import { useDebounce } from '@/hooks/useDebounce'

interface SearchBarProps {
  /** Called with the debounced query string after 300ms of inactivity. */
  onDebouncedChange: (query: string) => void
  /** Optional placeholder text. */
  placeholder?: string
  /** Quick-search suggestion chips rendered below the input. */
  suggestions?: string[]
}

/**
 * Search input with built-in 300ms debounce for the Memory Explorer.
 */
export function SearchBar({
  onDebouncedChange,
  placeholder = 'Search your agent memory…',
  suggestions = [],
}: SearchBarProps) {
  const [value, setValue] = useState('')
  const debouncedValue = useDebounce(value, 300)

  useEffect(() => {
    onDebouncedChange(debouncedValue)
  }, [debouncedValue, onDebouncedChange])

  return (
    <div className="bg-white rounded-[8px] border border-black/[0.08] px-[18px] py-4 mb-5">
      <div className="flex gap-[10px] mb-[10px]">
        <div className="relative flex-1 flex items-center">
          <svg
            width="15"
            height="15"
            viewBox="0 0 15 15"
            fill="none"
            className="absolute left-3 text-nexus-muted flex-shrink-0 pointer-events-none"
          >
            <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.4" />
            <path d="M11 11l3 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder}
            className="w-full h-10 border-[1.5px] border-nexus-accent shadow-[0_0_0_3px_rgba(83,74,183,0.12)] rounded-[7px] pl-9 pr-3 text-[14px] text-nexus-dark font-sans outline-none placeholder:text-nexus-subtle focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)] transition-[border-color,box-shadow]"
          />
        </div>
        <button
          type="button"
          onClick={() => onDebouncedChange(value)}
          className="bg-nexus-accent hover:bg-nexus-accent-hover text-white border-none h-10 px-[18px] rounded-[7px] text-[13.5px] font-medium font-sans flex items-center gap-[6px] transition-colors cursor-pointer flex-shrink-0"
        >
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <circle cx="5.5" cy="5.5" r="4" stroke="white" strokeWidth="1.4" />
            <path d="M9 9l3 3" stroke="white" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
          Search
        </button>
      </div>
      {suggestions.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[12px] text-nexus-muted">Try:</span>
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setValue(s)}
              className="bg-[#F0EFE9] text-nexus-accent px-[9px] py-[2px] rounded-[4px] text-[12px] font-medium cursor-pointer border border-nexus-accent/15 hover:bg-nexus-accent/5 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}