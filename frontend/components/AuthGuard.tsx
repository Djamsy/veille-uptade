'use client'

import { useState, useEffect, useRef, createContext, useContext } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { fetchCurrentUser } from '../lib/api'

// ── Types ──────────────────────────────────────────────
export interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'editor' | 'viewer' | 'user'
}

interface AuthContextType {
  user: User | null
  loading: boolean
  logout: () => void
}

// ── Context ────────────────────────────────────────────
const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  logout: () => {},
})

export const useAuth = () => useContext(AuthContext)

// ── Role hierarchy (higher = more permissions) ─────────
const ROLE_LEVEL: Record<string, number> = {
  user: 1,
  viewer: 2,
  editor: 3,
  admin: 4,
}

// ── Page → minimum role mapping ────────────────────────
const PAGE_ROLES: Record<string, string> = {
  '/admin': 'admin',
  '/analytics': 'viewer',
  '/affairs': 'user',
  '/articles': 'user',
  '/radio': 'user',
  '/elections': 'user',
  '/social': 'admin',
  '/admin/presence': 'admin',
  '/admin/affairs-monitor': 'admin',
  '/departement': 'user',
  '/region': 'user',
  '/dashboard': 'user',
  '/': 'user',
}

function hasAccess(userRole: string, requiredRole: string): boolean {
  return (ROLE_LEVEL[userRole] || 0) >= (ROLE_LEVEL[requiredRole] || 0)
}

// ── Public routes (no auth needed) ─────────────────────
const PUBLIC_ROUTES = ['/auth/login', '/auth/register']

// ── Dev bypass (opt-in via env, never on by default) ───
const DEV_BYPASS = process.env.NEXT_PUBLIC_DEV_BYPASS_AUTH === 'true'
const DEV_USER: User = {
  id: 'dev-user',
  email: 'dev@local',
  name: 'Dev Admin',
  role: 'admin',
}

// ════════════════════════════════════════════════════════
// AuthGuard Component
// ════════════════════════════════════════════════════════
export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [accessDenied, setAccessDenied] = useState(false)
  const router = useRouter()
  const pathname = usePathname()
  const checkedRef = useRef(false)

  const logout = () => {
    if (DEV_BYPASS) {
      // No-op in dev: there's no real auth to drop. Reload re-applies bypass.
      window.location.reload()
      return
    }
    localStorage.removeItem('token')
    setUser(null)
    router.push('/auth/login')
  }

  useEffect(() => {
    // Dev bypass: short-circuit auth check with a fake admin user
    if (DEV_BYPASS) {
      // If we land on an auth page in bypass mode, bounce to home
      if (PUBLIC_ROUTES.some(r => pathname.startsWith(r))) {
        router.replace('/')
        return
      }
      setUser(DEV_USER)
      setLoading(false)
      return
    }

    // Don't check auth on public routes
    if (PUBLIC_ROUTES.some(r => pathname.startsWith(r))) {
      setLoading(false)
      return
    }

    async function checkAuth() {
      const token = localStorage.getItem('token')

      if (!token) {
        router.push('/auth/login')
        return
      }

      try {
        const data = await fetchCurrentUser()
        if (data.success && data.user) {
          setUser(data.user as User)

          // Check role-based access for current page
          const matchedRoute = Object.keys(PAGE_ROLES)
            .filter(r => r !== '/')
            .find(r => pathname.startsWith(r))
          const requiredRole = PAGE_ROLES[matchedRoute || '/'] || 'user'

          if (!hasAccess(data.user.role, requiredRole)) {
            setAccessDenied(true)
          } else {
            setAccessDenied(false)
          }
        } else {
          localStorage.removeItem('token')
          router.push('/auth/login')
        }
      } catch {
        localStorage.removeItem('token')
        router.push('/auth/login')
      } finally {
        setLoading(false)
      }
    }

    checkAuth()
  }, [pathname, router])

  // Public routes: render children directly
  if (PUBLIC_ROUTES.some(r => pathname.startsWith(r))) {
    return <>{children}</>
  }

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-base)' }}>
        <div className="text-center">
          <div
            className="w-12 h-12 rounded-md flex items-center justify-center mx-auto mb-4"
            style={{ background: 'var(--brand-gradient)' }}
          >
            <span className="font-serif text-lg font-semibold text-white">VM</span>
          </div>
          <div className="flex items-center gap-2 text-sm font-mono" style={{ color: 'var(--text-muted)' }}>
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            Vérification…
          </div>
        </div>
      </div>
    )
  }

  // Access denied
  if (accessDenied) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-base)' }}>
        <div className="glass-card-static p-8 max-w-md text-center">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center mx-auto mb-4"
            style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)' }}>
            <svg className="w-7 h-7 text-[#f87171]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-white mb-2">Accès refusé</h2>
          <p className="text-sm mb-6" style={{ color: 'rgba(255,255,255,0.4)' }}>
            Votre rôle ({user?.role}) ne permet pas d'accéder à cette page.
          </p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => router.push('/')}
              className="btn-glass px-4 py-2 text-sm"
            >
              Tableau de bord
            </button>
            <button
              onClick={logout}
              className="btn-glass px-4 py-2 text-sm text-[#f87171]"
            >
              Se déconnecter
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <AuthContext.Provider value={{ user, loading, logout }}>
      {DEV_BYPASS && (
        <div
          className="fixed top-0 left-0 right-0 z-[100] text-center text-[10px] font-bold uppercase tracking-widest py-1"
          style={{ background: '#DC2626', color: 'white', letterSpacing: '0.2em' }}
        >
          ⚠ Mode dev — auth bypassée (NEXT_PUBLIC_DEV_BYPASS_AUTH)
        </div>
      )}
      {children}
    </AuthContext.Provider>
  )
}
