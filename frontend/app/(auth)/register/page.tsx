// frontend/app/(auth)/register/page.tsx
'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { setToken } from '@/lib/auth'

function getPasswordStrength(password: string): 'weak' | 'medium' | 'strong' | null {
  if (!password) return null
  const hasUpper = /[A-Z]/.test(password)
  const hasNumber = /[0-9]/.test(password)
  const hasSpecial = /[^A-Za-z0-9]/.test(password)
  const hasLength = password.length >= 8
  const score = [hasUpper, hasNumber, hasSpecial, hasLength].filter(Boolean).length
  if (score <= 1) return 'weak'
  if (score <= 3) return 'medium'
  return 'strong'
}

export default function RegisterPage(): JSX.Element {
  const router = useRouter()
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)

  const strength = getPasswordStrength(password)

  const rules = [
    { label: 'At least 8 characters', met: password.length >= 8 },
    { label: 'Uppercase letter', met: /[A-Z]/.test(password) },
    { label: 'Number', met: /[0-9]/.test(password) },
    { label: 'Special character', met: /[^A-Za-z0-9]/.test(password) },
  ]

  function validate(): boolean {
    const errs: Record<string, string> = {}
    if (!displayName.trim()) errs.displayName = 'Name is required'
    if (!email) errs.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = 'Enter a valid email address'
    if (!password) errs.password = 'Password is required'
    if (!agreed) errs.agreed = 'You must accept the terms to continue'
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    setError('')
    if (!validate()) return

    setLoading(true)
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/register`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, display_name: displayName }),
        }
      )
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        if (res.status === 409) {
          setFieldErrors(prev => ({ ...prev, email: 'This email is already registered' }))
          setError('An account with this email already exists.')
        } else {
          setError(body?.detail ?? 'Registration failed. Please try again.')
        }
        return
      }
      // Auto-login: register returns user info, then login to get token
      const loginRes = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/login`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        }
      )
      if (loginRes.ok) {
        const tokenData = await loginRes.json()
        setToken(tokenData.access_token)
        router.push('/dashboard')
      } else {
        router.push('/login')
      }
    } catch {
      setError('Unable to reach server. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const strengthConfig = {
    weak: { width: '33%', bg: '#E24B4A', label: 'Weak password', labelColor: '#E24B4A' },
    medium: { width: '66%', bg: '#BA7517', label: 'Medium strength', labelColor: '#BA7517' },
    strong: { width: '100%', bg: '#1D9E75', label: 'Strong password', labelColor: '#1D9E75' },
  }

  return (
    <main
      className="min-h-screen flex items-center justify-center px-6 py-10"
      style={{
        backgroundColor: '#E8E7E3',
        backgroundImage:
          'linear-gradient(rgba(83,74,183,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(83,74,183,0.04) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}
    >
      <div className="w-full max-w-[400px]">
        <div className="bg-white rounded-xl border border-black/[0.08] shadow-[0_4px_32px_rgba(0,0,0,0.10)]" style={{ padding: '36px 36px 32px' }}>
          {/* Brand stripe */}
          <div className="h-[3px] bg-nexus-accent rounded-t-xl" style={{ marginLeft: '-36px', marginRight: '-36px', marginTop: '-36px', marginBottom: '32px' }} />

          {/* Wordmark */}
          <div className="flex items-center gap-[10px] mb-7">
            <div className="w-8 h-8 bg-nexus-accent rounded-[7px] flex items-center justify-center flex-shrink-0">
              <svg viewBox="0 0 14 14" fill="none" className="w-[18px] h-[18px]">
                <rect x="1" y="1" width="5" height="5" rx="1" fill="white"/>
                <rect x="8" y="1" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
                <rect x="1" y="8" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
                <rect x="8" y="8" width="5" height="5" rx="1" fill="white" opacity="0.3"/>
              </svg>
            </div>
            <span className="text-[17px] font-bold text-nexus-dark tracking-[0.06em]">NEXUS</span>
          </div>

          <h1 className="text-[20px] font-semibold text-nexus-dark mb-1">Create an account</h1>
          <p className="text-[13.5px] text-nexus-muted mb-7">Start orchestrating AI agents in minutes.</p>

          {/* API-level error alert */}
          {error && !fieldErrors.email && (
            <div className="flex items-start gap-[9px] bg-[#FDECEA] border border-[rgba(226,75,74,0.2)] rounded-[7px] px-[13px] py-[10px] mb-[18px]">
              <svg width="15" height="15" viewBox="0 0 15 15" fill="none" className="flex-shrink-0 mt-[1px]">
                <circle cx="7.5" cy="7.5" r="6" stroke="#E24B4A" strokeWidth="1.4"/>
                <path d="M7.5 5v3" stroke="#E24B4A" strokeWidth="1.5" strokeLinecap="round"/>
                <circle cx="7.5" cy="10" r="0.8" fill="#E24B4A"/>
              </svg>
              <span className="text-[13px] text-nexus-error leading-[1.5]">{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            {/* Full name */}
            <div>
              <label htmlFor="displayName" className="block text-[11.5px] font-semibold text-nexus-muted uppercase tracking-[0.05em] mb-[6px]">Full name</label>
              <input
                id="displayName"
                type="text"
                autoComplete="name"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                disabled={loading}
                placeholder="Aryan Kumar"
                className={`w-full h-10 border rounded-[7px] px-3 text-[13.5px] text-nexus-dark font-sans outline-none bg-white placeholder:text-nexus-subtle transition-[border-color,box-shadow] focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)] disabled:bg-[#F5F4F0] disabled:cursor-not-allowed ${fieldErrors.displayName ? 'border-nexus-error shadow-[0_0_0_3px_rgba(226,75,74,0.1)]' : 'border-black/[0.12]'}`}
              />
              {fieldErrors.displayName && <FieldError message={fieldErrors.displayName} />}
            </div>

            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-[11.5px] font-semibold text-nexus-muted uppercase tracking-[0.05em] mb-[6px]">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                disabled={loading}
                placeholder="you@example.com"
                className={`w-full h-10 border rounded-[7px] px-3 text-[13.5px] text-nexus-dark font-sans outline-none bg-white placeholder:text-nexus-subtle transition-[border-color,box-shadow] focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)] disabled:bg-[#F5F4F0] disabled:cursor-not-allowed ${fieldErrors.email ? 'border-nexus-error shadow-[0_0_0_3px_rgba(226,75,74,0.1)]' : 'border-black/[0.12]'}`}
              />
              {fieldErrors.email && <FieldError message={fieldErrors.email} />}
            </div>

            {/* Password + strength */}
            <div>
              <label htmlFor="password" className="block text-[11.5px] font-semibold text-nexus-muted uppercase tracking-[0.05em] mb-[6px]">Password</label>
              <div className="relative flex items-center">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  disabled={loading}
                  placeholder="Min. 8 characters"
                  className={`w-full h-10 border rounded-[7px] px-3 pr-10 text-[13.5px] text-nexus-dark font-sans outline-none bg-white placeholder:text-nexus-subtle transition-[border-color,box-shadow] focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)] disabled:bg-[#F5F4F0] disabled:cursor-not-allowed ${fieldErrors.password ? 'border-nexus-error shadow-[0_0_0_3px_rgba(226,75,74,0.1)]' : 'border-black/[0.12]'}`}
                />
                <button type="button" onClick={() => setShowPassword(v => !v)} className="absolute right-[11px] text-nexus-muted hover:text-nexus-dark p-1 rounded">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" stroke="currentColor" strokeWidth="1.3"/><circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3"/></svg>
                </button>
              </div>
              {fieldErrors.password && <FieldError message={fieldErrors.password} />}

              {/* Strength meter */}
              {password && strength && (
                <div className="mt-[6px]">
                  <div className="h-[3px] bg-[#F0EFE9] rounded-[2px] overflow-hidden mb-1">
                    <div className="h-full rounded-[2px] transition-all duration-300" style={{ width: strengthConfig[strength].width, background: strengthConfig[strength].bg }} />
                  </div>
                  <span className="text-[11.5px] font-medium" style={{ color: strengthConfig[strength].labelColor }}>{strengthConfig[strength].label}</span>
                  <div className="flex flex-col gap-1 mt-2">
                    {rules.map(r => (
                      <div key={r.label} className={`flex items-center gap-[6px] text-[12px] ${r.met ? 'text-nexus-success' : 'text-nexus-subtle'}`}>
                        {r.met ? (
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        ) : (
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M9 3L3 9M3 3l6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                        )}
                        {r.label}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Terms */}
            <div>
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} className="w-[14px] h-[14px] mt-[2px] accent-nexus-accent cursor-pointer flex-shrink-0" />
                <span className="text-[13px] text-nexus-muted">
                  I agree to the{' '}
                  <Link href="/terms" className="text-nexus-accent font-medium no-underline hover:underline">Terms of Service</Link>
                  {' '}and{' '}
                  <Link href="/privacy" className="text-nexus-accent font-medium no-underline hover:underline">Privacy Policy</Link>
                </span>
              </label>
              {fieldErrors.agreed && <FieldError message={fieldErrors.agreed} />}
            </div>

            <button
              type="submit"
              disabled={loading || strength === 'weak' || !strength}
              className="w-full h-[42px] bg-nexus-accent hover:bg-nexus-accent-hover disabled:bg-nexus-subtle disabled:cursor-not-allowed text-white border-none rounded-[7px] text-[14px] font-medium font-sans flex items-center justify-center gap-2 transition-colors mt-[6px]"
            >
              {loading ? (
                <>
                  <span className="w-[15px] h-[15px] border-2 border-white/35 border-t-white rounded-full animate-spin flex-shrink-0" />
                  Creating account…
                </>
              ) : 'Create account'}
            </button>
          </form>

          <p className="text-center mt-[22px] text-[13px] text-nexus-muted">
            Already have an account?{' '}
            <Link href="/login" className="text-nexus-accent font-medium no-underline hover:underline">Sign in</Link>
          </p>
        </div>
      </div>
    </main>
  )
}

function FieldError({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-[5px] text-[12px] text-nexus-error font-medium mt-[5px]">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.3"/><path d="M6 4v2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><circle cx="6" cy="8.5" r="0.7" fill="currentColor"/></svg>
      {message}
    </div>
  )
}