'use client'

import { useEffect, useState } from 'react'

/**
 * Returns a debounced copy of `value` that only updates after
 * `delayMs` milliseconds of inactivity.
 *
 * @param value - The value to debounce.
 * @param delayMs - Debounce delay in milliseconds (default 300).
 */
export function useDebounce<T>(value: T, delayMs: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delayMs)

    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debouncedValue
}