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

      if (response.ok && data.success) {
        setSuccess('Inscription réussie ! Redirection…')
        setTimeout(() => router.push('/auth/login'), 2000)
      } else {
        setError(data.detail || data.error || data.message || `Erreur ${response.status}`)
      }
    } catch {
      setError('Impossible de contacter le serveur. Vérifiez votre connexion.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--bg-base)' }}>
      {/* Left — brand pitch */}
      <div
        className="hidden lg:flex flex-col flex-[1] p-16 relative overflow-hidden"
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
          <div className="font-mono text-[11px] uppercase tracking-[0.14em] mb-4" style={{ color: 'var(--text-muted)' }}>
            Création de compte
          </div>
          <h1 className="font-serif text-4xl xl:text-5xl font-medium tracking-tight italic leading-[1.05] max-w-[520px]" style={{ color: 'var(--text)' }}>
            Rejoignez-nous.
          </h1>
          <p className="mt-5 text-base leading-relaxed max-w-[460px]" style={{ color: 'var(--text-secondary)' }}>
            Accédez à la plateforme de veille médiatique la plus avancée de Guadeloupe.
            Suivi automatique, alertes intelligentes et analyses prédictives.
          </p>

          <div className="mt-10 space-y-2 max-w-[460px]">
            {[
              'Alertes personnalisées',
              'Tableaux de bord avancés',
              'Analyses prédictives IA',
            ].map(label => (
              <div
                key={label}
                className="flex items-center gap-2.5 px-3.5 py-2.5"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent-press)' }} />
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
          © 2026 Veille Média Guadeloupe
        </div>
      </div>

      {/* Right — form */}
      <div
        className="flex-1 lg:flex-[0_0_460px] flex flex-col justify-center px-6 sm:px-12 py-16"
        style={{ background: 'var(--bg-elevated)' }}
      >
        <div className="w-full max-w-sm mx-auto">
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

          <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
            Inscription
          </div>
          <h2 className="font-serif text-3xl font-medium italic tracking-tight" style={{ color: 'var(--text)' }}>
            Créer un compte
          </h2>
          <p className="mt-1.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
            Rejoignez la plateforme.
          </p>

          {error && (
            <div className="mt-6 px-3 py-2.5 text-xs" style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}>
              {error}
            </div>
          )}

          {success && (
            <div className="mt-6 px-3 py-2.5 text-xs" style={{ background: 'var(--ok-soft)', color: '#3d6f44', border: '1px solid #cce5d0', borderRadius: 'var(--radius-sm)' }}>
              {success}
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 space-y-3.5">
            {[
              { id: 'name', label: 'Nom complet', value: name, set: setName, type: 'text', placeholder: 'Jean Dupont', autoComplete: 'name' },
              { id: 'email', label: 'Email', value: email, set: setEmail, type: 'email', placeholder: 'jean@example.com', autoComplete: 'email' },
            ].map(f => (
              <div key={f.id}>
                <label htmlFor={f.id} className="block font-mono text-[10px] uppercase tracking-[0.14em] mb-1.5" style={{ color: 'var(--text-muted)' }}>
                  {f.label}
                </label>
                <input
                  id={f.id}
                  type={f.type}
                  value={f.value}
                  onChange={e => f.set(e.target.value)}
                  placeholder={f.placeholder}
                  required
                  disabled={loading}
                  autoComplete={f.autoComplete}
                  className="w-full px-3.5 py-2.5 text-sm focus:outline-none"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)' }}
                />
              </div>
            ))}

            <div>
              <label htmlFor="password" className="block font-mono text-[10px] uppercase tracking-[0.14em] mb-1.5" style={{ color: 'var(--text-muted)' }}>
                Mot de passe
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  disabled={loading}
                  autoComplete="new-password"
                  className="w-full px-3.5 py-2.5 pr-10 text-sm focus:outline-none"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--text-muted)' }}
                  tabIndex={-1}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>
              </div>
              <p className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>Au moins 6 caractères</p>
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block font-mono text-[10px] uppercase tracking-[0.14em] mb-1.5" style={{ color: 'var(--text-muted)' }}>
                Confirmer le mot de passe
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                required
                disabled={loading}
                autoComplete="new-password"
                className="w-full px-3.5 py-2.5 text-sm focus:outline-none"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)' }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 text-sm font-semibold rounded-sm transition-colors disabled:opacity-50 mt-1"
              style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Création…
                </span>
              ) : 'Créer le compte'}
            </button>
          </form>

          <p className="text-center text-sm mt-6" style={{ color: 'var(--text-secondary)' }}>
            Déjà un compte ?{' '}
            <Link href="/auth/login" className="font-semibold hover:underline" style={{ color: 'var(--text)' }}>
              Se connecter
            </Link>
          </p>

          <div className="mt-10 text-center font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
            © 2026 Veille Média Guadeloupe
          </div>
        </div>
      </div>
    </div>
  )
}
