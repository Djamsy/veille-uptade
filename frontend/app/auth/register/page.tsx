'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export default function RegisterPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    if (!name || !email || !password || !confirmPassword) {
      setError('Veuillez remplir tous les champs')
      return
    }

    if (password !== confirmPassword) {
      setError('Les mots de passe ne correspondent pas')
      return
    }

    if (password.length < 6) {
      setError('Le mot de passe doit contenir au moins 6 caractères')
      return
    }

    setLoading(true)

    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
      })

      const data = await response.json()

      if (data.success) {
        setSuccess('Inscription réussie ! Redirection...')
        setTimeout(() => router.push('/auth/login'), 2000)
      } else {
        setError(data.error || 'Erreur lors de l\'inscription')
      }
    } catch (err: any) {
      setError('Impossible de contacter le serveur')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex relative overflow-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 z-0">
        <div className="absolute top-[-20%] right-[-10%] w-[600px] h-[600px] rounded-full opacity-30"
          style={{ background: 'radial-gradient(circle, rgba(22,163,74,0.12) 0%, transparent 70%)', filter: 'blur(60px)' }} />
        <div className="absolute bottom-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, rgba(37,99,235,0.1) 0%, transparent 70%)', filter: 'blur(60px)' }} />
      </div>

      {/* Left side — Brand panel (desktop only) */}
      <div className="hidden lg:flex lg:w-[45%] flex-col justify-center items-center relative z-10 p-12"
        style={{ background: 'linear-gradient(135deg, rgba(22,163,74,0.06), rgba(37,99,235,0.04))' }}>
        <div className="max-w-md text-center">
          <div className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-8"
            style={{
              background: 'linear-gradient(135deg, #2563eb 0%, #eab308 50%, #16a34a 100%)',
              boxShadow: '0 8px 32px rgba(37,99,235,0.35)',
            }}>
            <span className="text-2xl font-bold text-white tracking-tight">VM</span>
          </div>

          <h1 className="text-3xl font-bold text-white mb-3 tracking-tight">Rejoignez-nous</h1>
          <p className="text-sm uppercase tracking-[0.25em] font-semibold mb-8" style={{ color: 'rgba(22,163,74,0.6)' }}>
            Guadeloupe
          </p>

          <p className="text-sm leading-relaxed mb-10" style={{ color: 'rgba(255,255,255,0.45)' }}>
            Accédez à la plateforme de veille médiatique la plus avancée de Guadeloupe. Suivi automatique, alertes intelligentes et analyses prédictives.
          </p>

          <div className="space-y-3 text-left">
            {[
              { label: 'Alertes personnalisées', color: '#60a5fa' },
              { label: 'Tableaux de bord avancés', color: '#facc15' },
              { label: 'Analyses prédictives IA', color: '#34d399' },
            ].map((f, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5 rounded-xl"
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <span className="text-[8px]" style={{ color: f.color }}>◆</span>
                <span className="text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>{f.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right side — Register form */}
      <div className="flex-1 flex flex-col justify-center items-center px-6 sm:px-12 relative z-10">
        <div className="w-full max-w-sm">

          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-6">
            <div className="w-14 h-14 rounded-xl flex items-center justify-center mx-auto mb-4"
              style={{
                background: 'linear-gradient(135deg, #2563eb 0%, #eab308 50%, #16a34a 100%)',
                boxShadow: '0 4px 20px rgba(37,99,235,0.3)',
              }}>
              <span className="text-lg font-bold text-white">VM</span>
            </div>
            <h1 className="text-xl font-bold text-white">Veille Média</h1>
            <p className="text-[9px] uppercase tracking-[0.2em] font-semibold" style={{ color: 'rgba(22,163,74,0.5)' }}>Guadeloupe</p>
          </div>

          {/* Register card */}
          <div className="glass-card-static p-7">
            <h2 className="text-lg font-semibold text-white mb-1">Créer un compte</h2>
            <p className="text-xs mb-5" style={{ color: 'rgba(255,255,255,0.3)' }}>Rejoignez la plateforme</p>

            {error && (
              <div className="mb-4 px-3 py-2.5 rounded-lg text-xs" style={{
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)', color: '#f87171',
              }}>{error}</div>
            )}

            {success && (
              <div className="mb-4 px-3 py-2.5 rounded-lg text-xs" style={{
                background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.15)', color: '#34d399',
              }}>{success}</div>
            )}

            <form onSubmit={handleSubmit} className="space-y-3.5">
              <div>
                <label htmlFor="name" className="block text-[11px] font-medium mb-1.5" style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Nom complet
                </label>
                <input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input-dark w-full px-3.5 py-2.5 text-sm"
                  placeholder="Jean Dupont"
                  required
                  disabled={loading}
                  autoComplete="name"
                />
              </div>

              <div>
                <label htmlFor="email" className="block text-[11px] font-medium mb-1.5" style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="input-dark w-full px-3.5 py-2.5 text-sm"
                  placeholder="jean@example.com"
                  required
                  disabled={loading}
                  autoComplete="email"
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-[11px] font-medium mb-1.5" style={{ color: 'rgba(255,255,255,0.4)' }}>
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
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2"
                    style={{ color: 'rgba(255,255,255,0.25)' }}
                    tabIndex={-1}
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  </button>
                </div>
                <p className="text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.2)' }}>Au moins 6 caractères</p>
              </div>

              <div>
                <label htmlFor="confirmPassword" className="block text-[11px] font-medium mb-1.5" style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Confirmer le mot de passe
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="input-dark w-full px-3.5 py-2.5 text-sm"
                  placeholder="••••••••"
                  required
                  disabled={loading}
                  autoComplete="new-password"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full py-2.5 text-sm mt-1"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    Création...
                  </span>
                ) : 'Créer le compte'}
              </button>
            </form>
          </div>

          {/* Login link */}
          <p className="text-center text-xs mt-5" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Déjà un compte ?{' '}
            <Link href="/auth/login" className="font-medium transition-colors" style={{ color: '#60a5fa' }}>
              Se connecter
            </Link>
          </p>

          <p className="text-center text-[10px] mt-8" style={{ color: 'rgba(255,255,255,0.15)' }}>
            &copy; 2025 Veille Média Guadeloupe
          </p>
        </div>
      </div>
    </div>
  )
}
