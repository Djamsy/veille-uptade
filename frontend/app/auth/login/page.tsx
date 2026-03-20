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
    } catch (err: any) {
      setError('Impossible de contacter le serveur. Vérifiez votre connexion.')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex relative overflow-hidden" style={{ background: '#060a13' }}>
      {/* Ambient background — tropical vibes */}
      <div className="absolute inset-0 z-0">
        {/* Bleu outremer */}
        <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full opacity-40"
          style={{ background: 'radial-gradient(circle, rgba(37,99,235,0.2) 0%, transparent 70%)', filter: 'blur(80px)' }} />
        {/* Vert tropical */}
        <div className="absolute bottom-[-15%] right-[-5%] w-[500px] h-[500px] rounded-full opacity-30"
          style={{ background: 'radial-gradient(circle, rgba(22,163,74,0.15) 0%, transparent 70%)', filter: 'blur(80px)' }} />
        {/* Soleil jaune */}
        <div className="absolute top-[20%] right-[30%] w-[400px] h-[400px] rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, rgba(234,179,8,0.1) 0%, transparent 60%)', filter: 'blur(60px)' }} />
      </div>

      {/* Left side — Brand panel (desktop only) */}
      <div className="hidden lg:flex lg:w-[48%] flex-col justify-center items-center relative z-10 p-12"
        style={{ background: 'linear-gradient(135deg, rgba(37,99,235,0.06), rgba(22,163,74,0.04), rgba(234,179,8,0.02))' }}>
        <div className="max-w-md text-center">
          {/* Logo */}
          <div className="w-24 h-24 rounded-2xl flex items-center justify-center mx-auto mb-8 relative"
            style={{
              background: 'linear-gradient(135deg, #16a34a 0%, #2563eb 50%, #eab308 100%)',
              boxShadow: '0 8px 40px rgba(37,99,235,0.3), 0 0 60px rgba(22,163,74,0.15)',
            }}>
            <span className="text-3xl font-black text-white tracking-tighter" style={{ textShadow: '0 2px 4px rgba(0,0,0,0.3)' }}>VM</span>
          </div>

          <h1 className="text-4xl font-black text-white mb-2 tracking-tight">Veille Média</h1>
          {/* Flag stripe */}
          <div className="flag-stripe w-32 mx-auto mb-3" />
          <p className="text-sm font-bold tracking-[0.25em] uppercase mb-10"
            style={{ background: 'linear-gradient(90deg, #16a34a, #eab308, #dc2626)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Guadeloupe 971
          </p>

          <p className="text-sm leading-relaxed mb-10" style={{ color: 'rgba(255,255,255,0.4)' }}>
            Plateforme de veille mediatique intelligente. Suivi des affaires politiques, analyse de sentiment, BMG et alertes en temps reel.
          </p>

          {/* Feature highlights */}
          <div className="space-y-2.5 text-left">
            {[
              { label: 'Suivi automatique des affaires', color: '#16a34a', icon: '▸' },
              { label: 'Analyse IA predictive', color: '#2563eb', icon: '▸' },
              { label: 'Alertes critiques en temps reel', color: '#dc2626', icon: '▸' },
              { label: 'Veille reseaux sociaux', color: '#eab308', icon: '▸' },
            ].map((f, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 rounded-xl transition-all hover:translate-x-1"
                style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
                <span className="text-sm font-bold" style={{ color: f.color }}>{f.icon}</span>
                <span className="text-[13px] font-medium" style={{ color: 'rgba(255,255,255,0.5)' }}>{f.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right side — Login form */}
      <div className="flex-1 flex flex-col justify-center items-center px-6 sm:px-12 relative z-10">
        <div className="w-full max-w-sm">

          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-8">
            <div className="w-16 h-16 rounded-xl flex items-center justify-center mx-auto mb-4"
              style={{
                background: 'linear-gradient(135deg, #16a34a 0%, #2563eb 50%, #eab308 100%)',
                boxShadow: '0 4px 20px rgba(37,99,235,0.3)',
              }}>
              <span className="text-xl font-black text-white">VM</span>
            </div>
            <h1 className="text-2xl font-black text-white">Veille Média</h1>
            <div className="flag-stripe w-20 mx-auto mt-2 mb-1" />
            <p className="text-[10px] font-bold tracking-[0.2em] uppercase"
              style={{ background: 'linear-gradient(90deg, #16a34a, #eab308)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Guadeloupe 971
            </p>
          </div>

          {/* API Status */}
          <div className="flex items-center gap-2 mb-6 px-3 py-2.5 rounded-lg text-xs"
            style={{
              background: apiStatus === 'ok' ? 'rgba(22,163,74,0.08)' : apiStatus === 'error' ? 'rgba(220,38,38,0.08)' : 'rgba(255,255,255,0.03)',
              border: `1px solid ${apiStatus === 'ok' ? 'rgba(22,163,74,0.2)' : apiStatus === 'error' ? 'rgba(220,38,38,0.2)' : 'rgba(255,255,255,0.06)'}`,
              color: apiStatus === 'ok' ? '#4ade80' : apiStatus === 'error' ? '#f87171' : 'rgba(255,255,255,0.4)',
            }}>
            <div className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{
                background: apiStatus === 'ok' ? '#4ade80' : apiStatus === 'error' ? '#f87171' : 'rgba(255,255,255,0.3)',
                boxShadow: apiStatus === 'ok' ? '0 0 8px rgba(22,163,74,0.5)' : 'none',
              }} />
            {apiStatus === 'testing' ? 'Connexion au backend...' : apiStatus === 'ok' ? 'Backend connecte' : 'Backend inaccessible'}
          </div>

          {/* Login card */}
          <div className="glass-card-static p-7" style={{ borderColor: 'rgba(37,99,235,0.1)' }}>
            {/* Top accent */}
            <div className="absolute top-0 left-0 right-0 h-[3px] rounded-t-2xl"
              style={{ background: 'linear-gradient(90deg, #16a34a, #eab308, #dc2626)' }} />

            <h2 className="text-lg font-bold text-white mb-1">Connexion</h2>
            <p className="text-xs mb-6" style={{ color: 'rgba(255,255,255,0.3)' }}>Accedez a votre tableau de bord</p>

            {error && (
              <div className="mb-4 px-3 py-2.5 rounded-lg text-xs flex items-center gap-2" style={{
                background: 'rgba(220,38,38,0.1)',
                border: '1px solid rgba(220,38,38,0.2)',
                color: '#f87171',
              }}>
                <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
                </svg>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="email" className="block text-[11px] font-semibold mb-1.5 uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="input-dark w-full px-3.5 py-2.5 text-sm"
                  placeholder="votre@email.com"
                  required
                  disabled={loading}
                  autoComplete="email"
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-[11px] font-semibold mb-1.5 uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  Mot de passe
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="input-dark w-full px-3.5 py-2.5 pr-10 text-sm"
                    placeholder="••••••••"
                    required
                    disabled={loading}
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                    style={{ color: 'rgba(255,255,255,0.25)' }}
                    tabIndex={-1}
                  >
                    {showPassword ? (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                      </svg>
                    ) : (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full py-3 text-sm mt-2 font-bold"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    Connexion...
                  </span>
                ) : 'Se connecter'}
              </button>
            </form>
          </div>

          {/* Register link */}
          <p className="text-center text-xs mt-5" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Pas encore de compte ?{' '}
            <Link href="/auth/register" className="font-semibold transition-colors hover:text-white" style={{ color: '#60a5fa' }}>
              Creer un compte
            </Link>
          </p>

          {/* Footer */}
          <div className="text-center mt-8">
            <div className="flag-stripe w-12 mx-auto mb-2" />
            <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.12)' }}>
              &copy; 2025 Veille Media Guadeloupe
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
