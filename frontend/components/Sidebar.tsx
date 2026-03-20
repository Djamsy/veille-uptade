'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from './AuthGuard'

const navItems = [
  {
    href: '/',
    label: 'Dashboard',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    href: '/affairs',
    label: 'Affaires',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
  {
    href: '/radio',
    label: 'Radio',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" />
      </svg>
    ),
  },
  {
    href: '/social',
    label: 'Réseaux Sociaux',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
      </svg>
    ),
  },
  {
    href: '/elections',
    label: 'Elections',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
  },
  {
    href: '/departement',
    label: 'Département',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    href: '/region',
    label: 'Région',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    href: '/articles',
    label: 'Articles',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
      </svg>
    ),
  },
  {
    href: '/analytics',
    label: 'Analytics',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    href: '/profile',
    label: 'Profil',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    href: '/admin',
    label: 'Admin',
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
]

export default function Sidebar() {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { user, logout } = useAuth()

  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/'
    return pathname.startsWith(href)
  }

  const roleColor = (role: string) => {
    switch (role) {
      case 'admin': return '#dc2626'
      case 'editor': return '#eab308'
      case 'viewer': return '#2563eb'
      default: return '#16a34a'
    }
  }

  const sidebarContent = (
    <>
      {/* ── Logo + Brand ────────────────── */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center gap-3">
          {/* Logo — butterfly/sun shape */}
          <div className="w-10 h-10 rounded-xl flex items-center justify-center relative"
            style={{
              background: 'linear-gradient(135deg, #16a34a 0%, #2563eb 50%, #eab308 100%)',
              boxShadow: '0 4px 20px rgba(37,99,235,0.3), 0 0 30px rgba(22,163,74,0.15)',
            }}
          >
            <span className="text-sm font-black text-white tracking-tighter" style={{ textShadow: '0 1px 2px rgba(0,0,0,0.3)' }}>VM</span>
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-bold text-white leading-tight tracking-tight">Veille Média</h1>
            <p className="text-[10px] font-bold tracking-[0.15em] uppercase"
              style={{ background: 'linear-gradient(90deg, #16a34a, #eab308)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Guadeloupe 971
            </p>
          </div>
          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden ml-auto p-1.5 rounded-lg hover:bg-white/10 transition-colors"
            aria-label="Fermer le menu"
          >
            <svg className="w-4 h-4 text-white/40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {/* Flag stripe */}
        <div className="flag-stripe mt-4 w-full" />
      </div>

      {/* ── Navigation ──────────────────── */}
      <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        {navItems.filter(item => {
          if (item.href === '/admin' && user?.role !== 'admin') return false
          return true
        }).map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`sidebar-link flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all ${
              isActive(item.href)
                ? 'active text-white'
                : 'text-white/30 hover:text-white/70 hover:bg-white/[0.03]'
            }`}
            style={isActive(item.href) ? {
              background: 'rgba(37,99,235,0.1)',
            } : undefined}
            aria-current={isActive(item.href) ? 'page' : undefined}
          >
            <span className={`transition-colors ${isActive(item.href) ? 'text-blue-400' : ''}`}>
              {item.icon}
            </span>
            <span className="flex-1">{item.label}</span>
            {isActive(item.href) && (
              <span className="w-1.5 h-1.5 rounded-full"
                style={{
                  background: 'linear-gradient(135deg, #16a34a, #eab308)',
                  boxShadow: '0 0 8px rgba(234,179,8,0.4)',
                }} />
            )}
          </Link>
        ))}
      </nav>

      {/* ── Footer — User info + Logout ───── */}
      <div className="px-4 py-4 space-y-3" style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
        {user && (
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-[11px] font-bold text-white relative"
              style={{
                background: `linear-gradient(135deg, ${roleColor(user.role || 'user')}40, ${roleColor(user.role || 'user')}20)`,
                border: `1px solid ${roleColor(user.role || 'user')}50`,
              }}>
              {user.name?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] text-white/70 truncate leading-tight font-medium">{user.name || user.email}</p>
              <p className="text-[9px] uppercase tracking-wider font-bold" style={{ color: roleColor(user.role || 'user') }}>
                {user.role === 'admin' ? 'Administrateur' : user.role === 'editor' ? 'Editeur' : user.role === 'viewer' ? 'Visualiseur' : 'Utilisateur'}
              </p>
            </div>
          </div>
        )}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px]" style={{ color: 'rgba(255,255,255,0.3)' }}>
            <div className="w-1.5 h-1.5 rounded-full pulse-ring"
              style={{ background: '#16a34a', boxShadow: '0 0 8px rgba(22,163,74,0.5)', color: '#16a34a' }}
            />
            En ligne
          </div>
          <button
            onClick={logout}
            className="text-[10px] px-2.5 py-1.5 rounded-lg transition-all text-white/25 hover:text-red-400 hover:bg-red-500/10"
            title="Se deconnecter"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
            </svg>
          </button>
        </div>
      </div>
    </>
  )

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        onClick={() => setMobileOpen(true)}
        className="lg:hidden fixed top-4 left-4 z-50 p-2.5 rounded-xl transition-all active:scale-95"
        style={{
          background: 'rgba(6,10,19,0.85)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(37,99,235,0.15)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.3), 0 0 20px rgba(37,99,235,0.05)',
        }}
        aria-label="Ouvrir le menu"
      >
        <svg className="w-5 h-5 text-white/60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed left-0 top-0 h-screen w-60 flex-col z-40"
        style={{
          background: 'rgba(6,10,19,0.92)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderRight: '1px solid rgba(37,99,235,0.08)',
        }}
      >
        {sidebarContent}
      </aside>

      {/* Mobile sidebar */}
      <aside
        className={`lg:hidden fixed left-0 top-0 h-screen w-72 flex flex-col z-50 transform transition-transform duration-300 ease-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        style={{
          background: 'rgba(6,10,19,0.98)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderRight: '1px solid rgba(37,99,235,0.12)',
        }}
      >
        {sidebarContent}
      </aside>
    </>
  )
}
