// frontend/app/(auth)/login/page.tsx
'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { setToken } from '@/lib/auth'


export default function LoginPage(): JSX.Element {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    setError('')

    if (!email) { setError('Email is required'); return }
    if (!password) { setError('Password is required'); return }

    setLoading(true)
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/login`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        }
      )
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(
          res.status === 401
            ? 'Invalid email or password. Please check your credentials and try again.'
            : body?.detail ?? 'Login failed. Please try again.'
        )
        return
      }
      const data = await res.json()
      setToken(data.access_token, remember)
      router.push('/dashboard')
    } catch {
      setError('Unable to reach server. Please try again.')
    } finally {
      setLoading(false)
    }
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
        {/* Auth card */}
        <div
          className="bg-white rounded-xl border border-black/[0.08] shadow-[0_4px_32px_rgba(0,0,0,0.10)]"
          style={{ padding: '36px 36px 32px' }}
        >
          {/* Brand stripe */}
          <div
            className="h-[3px] bg-nexus-accent rounded-t-xl -mx-9 -mt-9 mb-8"
            style={{ marginLeft: '-36px', marginRight: '-36px', marginTop: '-36px' }}
          />

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

          <h1 className="text-[20px] font-semibold text-nexus-dark mb-1">Welcome back</h1>
          <p className="text-[13.5px] text-nexus-muted mb-7">Sign in to your account to continue.</p>

          {/* Auth error alert */}
          {error && (
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
            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-[11.5px] font-semibold text-nexus-muted uppercase tracking-[0.05em] mb-[6px]">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                disabled={loading}
                placeholder="you@example.com"
                className="w-full h-10 border border-black/[0.12] rounded-[7px] px-3 text-[13.5px] text-nexus-dark font-sans outline-none bg-white placeholder:text-nexus-subtle transition-[border-color,box-shadow] focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)] disabled:bg-[#F5F4F0] disabled:text-nexus-subtle disabled:cursor-not-allowed"
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-[11.5px] font-semibold text-nexus-muted uppercase tracking-[0.05em] mb-[6px]">
                Password
              </label>
              <div className="relative flex items-center">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  disabled={loading}
                  placeholder="••••••••"
                  className="w-full h-10 border border-black/[0.12] rounded-[7px] px-3 pr-10 text-[13.5px] text-nexus-dark font-sans outline-none bg-white placeholder:text-nexus-subtle transition-[border-color,box-shadow] focus:border-nexus-accent focus:shadow-[0_0_0_3px_rgba(83,74,183,0.12)] disabled:bg-[#F5F4F0] disabled:text-nexus-subtle disabled:cursor-not-allowed"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  className="absolute right-[11px] text-nexus-muted hover:text-nexus-dark p-1 rounded"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" stroke="currentColor" strokeWidth="1.3"/>
                    <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3"/>
                  </svg>
                </button>
              </div>
            </div>

            {/* Remember me */}
            <div className="flex items-center">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={e => setRemember(e.target.checked)}
                  className="w-[14px] h-[14px] accent-nexus-accent cursor-pointer"
                />
                <span className="text-[13px] text-nexus-muted">Remember me</span>
              </label>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full h-[42px] bg-nexus-accent hover:bg-nexus-accent-hover disabled:bg-nexus-subtle disabled:cursor-not-allowed text-white border-none rounded-[7px] text-[14px] font-medium font-sans flex items-center justify-center gap-2 transition-colors mt-[6px]"
            >
              {loading ? (
                <>
                  <span className="w-[15px] h-[15px] border-2 border-white/35 border-t-white rounded-full animate-spin flex-shrink-0" />
                  Signing in…
                </>
              ) : 'Sign in'}
            </button>
          </form>

          <p className="text-center mt-[22px] text-[13px] text-nexus-muted">
            Don&apos;t have an account?{' '}
            <Link href="/register" className="text-nexus-accent font-medium no-underline hover:underline">
              Register
            </Link>
          </p>
        </div>
      </div>
    </main>
  )
}