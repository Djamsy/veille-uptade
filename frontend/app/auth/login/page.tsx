'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { fetchHealth } from '../../../lib/api'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [apiStatus, setApiStatus] = useState<'testing' | 'ok' | 'error'>('testing')
  const [showPassword, setShowPassword] = useState(false)
  const router = useRouter()
  const hasTestedAPI = useRef(false)

  useEffect(() => {
    if (hasTestedAPI.current) return
    hasTestedAPI.current = true

    async function testAPI() {
      try {
        await fetchHealth()
        setApiStatus('ok')
      } catch {
        setApiStatus('error')
      }
    }
    testAPI()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (loading) return

    setLoading(true)
    setError('')

    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      const data = await response.json()

      if (response.ok && data.success) {
        localStorage.setItem('token', data.token)
        router.push('/')
      } else {
        setError(data.detail || data.error || 'Identifiants incorrects')
        setLoading(false)
      }
    } catch {
      setError('Impossible de contacter le serveur. Vérifiez votre connexion.')
      setLoading(false)
    }
  }

  const statusMeta = {
    testing: { bg: 'var(--bg-elevated)', color: 'var(--text-muted)', label: 'Connexion au backend…' },
    ok:      { bg: 'var(--ok-soft)',     color: '#3d6f44',           label: 'Backend connecté · pipeline opérationnel' },
    error:   { bg: 'var(--crit-soft)',   color: '#b02939',           label: 'Backend inaccessible' },
  }[apiStatus]

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--bg-base)' }}>
      {/* Left — brand / pitch (desktop only) */}
      <div
        className="hidden lg:flex flex-col flex-[1.1] p-16 relative overflow-hidden"
        style={{ background: 'var(--bg-base)', borderRight: '1px solid var(--border)' }}
      >
        <div className="absolute inset-x-0 top-0 h-[2px] opacity-70" style={{ background: 'var(--brand-gradient)' }} />

        <div className="flex items-center gap-3.5">
          <div
            className="w-11 h-11 rounded-lg flex items-center justify-center"
            style={{ background: 'var(--brand-gradient)' }}
          >
            <span className="font-serif text-base font-semibold text-white">VM</span>
          </div>
          <div>
            <div className="font-serif text-lg font-semibold tracking-tight" style={{ color: 'var(--text)' }}>
              Veille Média
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Guadeloupe · 971
            </div>
          </div>
        </div>

        <div className="my-auto">
          <div className="flex items-center gap-2 mb-4 font-mono text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--brand-gradient)' }} />
            Plateforme de veille institutionnelle
          </div>
          <h1
            className="font-serif text-4xl xl:text-5xl font-medium tracking-tight italic leading-[1.05] max-w-[520px]"
            style={{ color: 'var(--text)' }}
          >
            La parole publique, captée en temps réel.
          </h1>
          <p className="mt-5 text-base leading-relaxed max-w-[460px]" style={{ color: 'var(--text-secondary)' }}>
            Suivi des affaires, analyse de sentiment, BMG et alertes critiques pour les chargés de communication
            et attachés de presse des collectivités guadeloupéennes.
          </p>

          <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-[480px]">
            {[
              { t: 'Suivi automatique des affaires', d: '100 dossiers · scoring BMG' },
              { t: 'Captures radio quotidiennes', d: 'RCI + Guadeloupe 1ère' },
              { t: 'Veille réseaux sociaux', d: 'Buffer + Apify' },
              { t: 'Analyse IA prédictive', d: 'Sentiment + NER' },
            ].map(f => (
              <div
                key={f.t}
                className="p-3.5"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
              >
                <div className="text-sm font-medium" style={{ color: 'var(--text)' }}>{f.t}</div>
                <div className="font-mono text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>{f.d}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
          © 2026 Veille Média Guadeloupe
        </div>
      </div>

      {/* Right — login form */}
      <div
        className="flex-1 lg:flex-[0_0_460px] flex flex-col justify-center px-6 sm:px-12 py-16"
        style={{ background: 'var(--bg-elevated)' }}
      >
        <div className="w-full max-w-sm mx-auto">
          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-8">
            <div
              className="w-14 h-14 rounded-md flex items-center justify-center mx-auto mb-3"
              style={{ background: 'var(--brand-gradient)' }}
            >
              <span className="font-serif text-lg font-semibold text-white">VM</span>
            </div>
            <h1 className="font-serif text-2xl font-semibold tracking-tight" style={{ color: 'var(--text)' }}>
              Veille Média
            </h1>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] mt-1" style={{ color: 'var(--text-muted)' }}>
              Guadeloupe · 971
            </p>
          </div>

          {/* API status */}
          <div
            className="inline-flex items-center gap-2 px-3 py-2 text-xs font-mono mb-8"
            style={{ background: statusMeta.bg, color: statusMeta.color, border: `1px solid ${statusMeta.color}33`, borderRadius: 'var(--radius-sm)' }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: statusMeta.color }} />
            {statusMeta.label}
          </div>

          <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
            Accès
          </div>
          <h2 className="font-serif text-3xl font-medium italic tracking-tight" style={{ color: 'var(--text)' }}>
            Connexion
          </h2>
          <p className="mt-1.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
            Accédez à votre tableau de bord.
          </p>

          {error && (
            <div
              className="mt-6 px-3 py-2.5 text-xs"
              style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="email" className="block font-mono text-[10px] uppercase tracking-[0.14em] mb-1.5" style={{ color: 'var(--text-muted)' }}>
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="votre@email.com"
                required
                disabled={loading}
                autoComplete="email"
                className="w-full px-3.5 py-2.5 text-sm focus:outline-none focus:border-press"
                style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--text)',
                }}
              />
            </div>

            <div>
              <div className="flex justify-between mb-1.5">
                <label htmlFor="password" className="block font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                  Mot de passe
                </label>
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>Oublié ?</span>
              </div>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  disabled={loading}
                  autoComplete="current-password"
                  className="w-full px-3.5 py-2.5 pr-10 text-sm focus:outline-none"
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--text)',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--text-muted)' }}
                  tabIndex={-1}
                  aria-label={showPassword ? 'Masquer' : 'Afficher'}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                    {showPassword ? (
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                    ) : (
                      <>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </>
                    )}
                  </svg>
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 text-sm font-semibold rounded-sm transition-colors disabled:opacity-50 mt-2"
              style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Connexion…
                </span>
              ) : 'Se connecter'}
            </button>
          </form>

          <p className="text-center text-sm mt-6" style={{ color: 'var(--text-secondary)' }}>
            Pas encore de compte ?{' '}
            <Link href="/auth/register" className="font-semibold hover:underline" style={{ color: 'var(--text)' }}>
              Créer un compte
            </Link>
          </p>

          <div className="mt-10 flex justify-between font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
            <span>RGPD · CNIL conforme</span>
            <span>© 2026 Veille Média</span>
          </div>
        </div>
      </div>
    </div>
  )
}
