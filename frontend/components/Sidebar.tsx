'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from './AuthGuard'

type NavItem = {
  href: string
  label: string
  icon: React.ReactNode
  adminOnly?: boolean
}

type NavSection = {
  id: string
  label: string
  items: NavItem[]
}

const ICON = {
  dashboard: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
    </svg>
  ),
  affairs: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
  radio: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" />
    </svg>
  ),
  social: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
    </svg>
  ),
  observatoire: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 3v18h18M7 14l3.5-3.5 2.5 2.5L18 8m0 0h-3.5M18 8v3.5" />
    </svg>
  ),
  elections: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
  ),
  carte: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
    </svg>
  ),
  articles: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
    </svg>
  ),
  briefing: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2M9 12h6m-6 4h6" />
    </svg>
  ),
  analytics: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
  admin: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  departement: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
  ),
  region: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
}

// IA orientée JOB (pas par type de données) :
// Surveiller (le pouls) → Ma collectivité (le job n°1) → Sources → Partager → Système
const SECTIONS: NavSection[] = [
  {
    id: 'surveiller',
    label: 'Surveiller',
    items: [
      { href: '/', label: 'Vue d’ensemble', icon: ICON.dashboard },
      { href: '/affairs', label: 'Affaires', icon: ICON.affairs },
      { href: '/carte', label: 'Carte', icon: ICON.carte },
      { href: '/elections', label: 'Élections', icon: ICON.elections },
    ],
  },
  {
    id: 'collectivite',
    label: 'Ma collectivité',
    items: [
      { href: '/departement', label: 'Département', icon: ICON.departement },
      { href: '/region', label: 'Région', icon: ICON.region },
    ],
  },
  {
    id: 'sources',
    label: 'Sources',
    items: [
      { href: '/articles', label: 'Articles', icon: ICON.articles },
      { href: '/radio', label: 'Radio', icon: ICON.radio },
      { href: '/social', label: 'Campagnes', icon: ICON.social, adminOnly: true },
    ],
  },
  {
    id: 'partager',
    label: 'Analyser & partager',
    items: [
      { href: '/observatoire', label: 'Observatoire', icon: ICON.observatoire, adminOnly: true },
      { href: '/analytics', label: 'Analytics', icon: ICON.analytics },
      { href: '/briefing', label: 'Briefing', icon: ICON.briefing },
    ],
  },
  {
    id: 'admin',
    label: 'Système',
    items: [
      { href: '/admin', label: 'Admin', icon: ICON.admin, adminOnly: true },
    ],
  },
]

function roleColor(role: string) {
  switch (role) {
    case 'admin': return '#c43850'
    case 'editor': return '#b8632a'
    case 'viewer': return '#3e6fa3'
    default: return '#4f8b56'
  }
}

function NavLink({ item, isActive }: { item: NavItem; isActive: boolean }) {
  return (
    <Link
      href={item.href}
      className="flex items-center gap-3 px-2.5 py-2.5 rounded-lg transition-all group focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-press"
      style={isActive ? {
        background: 'var(--bg-hover)',
        color: 'var(--text)',
      } : {
        color: 'var(--text-muted)',
      }}
      title={item.label}
    >
      <span
        className="transition-colors"
        style={isActive ? { color: '#18181b' } : undefined}
      >
        {item.icon}
      </span>
      <span className="nav-label text-[13px] font-medium">{item.label}</span>
      {isActive && (
        <span
          className="nav-label ml-auto w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: '#18181b' }}
        />
      )}
    </Link>
  )
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="nav-label px-2.5 pt-3 pb-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.15em]" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
    </div>
  )
}

function filterSections(sections: NavSection[], isAdmin: boolean): NavSection[] {
  return sections
    .map(section => ({
      ...section,
      items: section.items.filter(item => !item.adminOnly || isAdmin),
    }))
    .filter(section => section.items.length > 0)
}

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

  const sections = filterSections(SECTIONS, user?.role === 'admin')

  return (
    <>
      {/* ── Mobile hamburger button ──────────────── */}
      <button
        onClick={() => setMobileOpen(true)}
        className="lg:hidden fixed top-4 left-4 z-50 p-2.5 rounded-xl transition-all active:scale-95"
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          boxShadow: 'var(--shadow-card)',
        }}
        aria-label="Ouvrir le menu"
      >
        <svg className="w-5 h-5" style={{ color: 'var(--text-secondary)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* ── Mobile overlay ───────────────────────── */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/70 backdrop-blur-sm transition-opacity"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ══ Desktop: Icon sidebar with expand on hover ══ */}
      <aside
        className="icon-sidebar hidden lg:flex fixed left-0 top-0 h-screen flex-col z-40 overflow-hidden"
        style={{
          background: 'var(--bg-surface)',
          borderRight: '1px solid var(--border)',
        }}
        aria-label="Navigation principale"
      >
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 px-3 pt-5 pb-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-press">
          <div
            className="w-10 h-10 shrink-0 rounded-lg flex items-center justify-center"
            style={{
              background: 'var(--brand-gradient)',
            }}
          >
            <span className="text-sm font-black text-white tracking-tighter">VM</span>
          </div>
          <div className="nav-label flex-1 min-w-0">
            <h1 className="font-serif text-base font-semibold leading-tight tracking-tight" style={{ color: 'var(--text)' }}>Veille Média</h1>
            <p className="font-serif text-[11px] italic leading-tight" style={{ color: 'var(--text-secondary)' }}>
              Guadeloupe · 971
            </p>
          </div>
        </Link>

        <div className="flag-stripe mx-3 mb-2" />

        {/* Navigation grouped by section */}
        <nav className="flex-1 px-2 py-1 overflow-y-auto scrollbar-hide">
          {sections.map(section => (
            <div key={section.id} className="mb-1">
              <SectionHeader label={section.label} />
              <div className="space-y-0.5">
                {section.items.map(item => (
                  <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer — User info */}
        <div className="px-2.5 py-3 space-y-2" style={{ borderTop: '1px solid var(--border)' }}>
          {user && (
            <div className="flex items-center gap-2.5">
              <div
                className="w-9 h-9 shrink-0 rounded-lg flex items-center justify-center text-[11px] font-bold"
                style={{
                  background: `linear-gradient(135deg, ${roleColor(user.role || 'user')}, ${roleColor(user.role || 'user')}80)`,
                  color: 'white',
                }}
              >
                {user.name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <div className="nav-label flex-1 min-w-0">
                <p className="text-[11px] truncate leading-tight font-medium" style={{ color: 'var(--text-secondary)' }}>
                  {user.name || user.email}
                </p>
                <p className="text-[9px] uppercase tracking-wider font-bold" style={{ color: roleColor(user.role || 'user') }}>
                  {user.role === 'admin' ? 'Admin' : user.role === 'editor' ? 'Editeur' : 'User'}
                </p>
              </div>
            </div>
          )}
          <div className="flex items-center justify-between px-0.5">
            <div className="flex items-center gap-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#16a34a', boxShadow: '0 0 6px rgba(22,163,74,0.5)' }} />
              <span className="nav-label">En ligne</span>
            </div>
            <button
              onClick={logout}
              className="p-1.5 rounded-lg transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-press"
              style={{ color: 'var(--text-muted)' }}
              title="Se déconnecter"
              aria-label="Se déconnecter"
              onMouseEnter={e => { e.currentTarget.style.color = 'var(--negative)'; e.currentTarget.style.background = 'var(--crit-soft)' }}
              onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.background = 'transparent' }}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* ══ Mobile: Full sidebar slide-in ══ */}
      <aside
        className={`lg:hidden fixed left-0 top-0 h-screen w-72 flex flex-col z-50 transform transition-transform duration-300 ease-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        style={{
          background: 'var(--bg-surface)',
          borderRight: '1px solid var(--border-hover)',
        }}
        aria-label="Navigation principale (mobile)"
      >
        {/* Mobile header */}
        <div className="flex items-center gap-3 px-5 pt-5 pb-4">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{
              background: 'var(--brand-gradient)',
            }}
          >
            <span className="text-sm font-black text-white tracking-tighter">VM</span>
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="font-serif text-base font-semibold leading-tight tracking-tight" style={{ color: 'var(--text)' }}>Veille Média</h1>
            <p className="font-serif text-[11px] italic leading-tight" style={{ color: 'var(--text-secondary)' }}>Guadeloupe · 971</p>
          </div>
          <button
            onClick={() => setMobileOpen(false)}
            className="p-1.5 rounded-lg transition-colors"
            style={{ color: 'var(--text-muted)' }}
            aria-label="Fermer le menu"
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flag-stripe mx-5 mb-2" />

        <nav className="flex-1 px-3 py-2 overflow-y-auto">
          {sections.map(section => (
            <div key={section.id} className="mb-2">
              <div className="px-3 pt-2 pb-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-[0.15em]" style={{ color: 'var(--text-muted)' }}>
                  {section.label}
                </span>
              </div>
              <div className="space-y-0.5">
                {section.items.map(item => {
                  const active = isActive(item.href)
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all"
                      style={active ? {
                        background: 'var(--bg-hover)',
                        color: 'var(--text)',
                      } : {
                        color: 'var(--text-muted)',
                      }}
                    >
                      <span style={active ? { color: '#18181b' } : undefined}>{item.icon}</span>
                      <span className="flex-1">{item.label}</span>
                      {active && (
                        <span
                          className="w-1.5 h-1.5 rounded-full"
                          style={{ background: '#18181b' }}
                        />
                      )}
                    </Link>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Mobile footer */}
        <div className="px-4 py-4 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
          {user && (
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-[11px] font-bold"
                style={{
                  background: `linear-gradient(135deg, ${roleColor(user.role || 'user')}, ${roleColor(user.role || 'user')}80)`,
                  color: 'white',
                }}>
                {user.name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[11px] truncate leading-tight font-medium" style={{ color: 'var(--text-secondary)' }}>{user.name || user.email}</p>
                <p className="text-[9px] uppercase tracking-wider font-bold" style={{ color: roleColor(user.role || 'user') }}>
                  {user.role === 'admin' ? 'Admin' : user.role === 'editor' ? 'Editeur' : 'User'}
                </p>
              </div>
              <button
                onClick={logout}
                className="p-2 rounded-lg transition-colors"
                style={{ color: 'var(--text-muted)' }}
                aria-label="Se déconnecter"
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--negative)'; e.currentTarget.style.background = 'var(--crit-soft)' }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.background = 'transparent' }}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
                </svg>
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
