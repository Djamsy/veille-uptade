'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { fetchHealth } from '../../../lib/api'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [apiStatus, setApiStatus] = useState('Test en cours...')
  const router = useRouter()
  const hasTestedAPI = useRef(false)

  useEffect(() => {
    if (hasTestedAPI.current) return
    hasTestedAPI.current = true

    async function testAPI() {
      try {
        await fetchHealth()
        setApiStatus('Backend connecté')
      } catch (err: any) {
        setApiStatus(`Backend inaccessible: ${err.message}`)
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

      if (data.success) {
        localStorage.setItem('token', data.token)
        router.push('/')
      } else {
        setError(data.error || 'Erreur de connexion')
        setLoading(false)
      }
    } catch (err: any) {
      setError('Erreur réseau: ' + err.message)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#faf9f6]">
      <div className="max-w-sm w-full">
        {/* API Status */}
        <div className={`px-3 py-2 rounded-lg text-xs mb-4 ${
          apiStatus.includes('connecté')
            ? 'bg-emerald-50 border border-emerald-200 text-emerald-600'
            : 'bg-amber-50 border border-amber-200 text-amber-600'
        }`}>
          {apiStatus}
        </div>

        {/* Login Card */}
        <div className="bg-white rounded-xl border border-slate-200 p-8 shadow-sm">
          {/* Logo */}
          <div className="flex items-center justify-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl bg-amber-400 flex items-center justify-center shadow-lg">
              <span className="text-lg">🏝️</span>
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-800">Veille Média</h1>
              <p className="text-[10px] text-teal-600 uppercase tracking-widest">Guadeloupe</p>
            </div>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-600 px-3 py-2 rounded-lg text-xs mb-4">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-xs font-medium text-slate-500 mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
                placeholder="test@example.com"
                required
                disabled={loading}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-medium text-slate-500 mb-1.5">
                Mot de passe
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
                placeholder="test123"
                required
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-teal-600 hover:bg-teal-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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

          <p className="mt-4 text-center text-[10px] text-slate-400">
            Compte test : test@example.com / test123
          </p>
        </div>
      </div>
    </div>
  )
}
