'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'
import { GuadeloupeMark } from '../../../components/GuadeloupeMark'
import { Icon, label } from './common'

export type Tab = 'flux' | 'mediatheque' | 'reglages'

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'flux', label: 'Flux' },
  { key: 'mediatheque', label: 'Médiathèque' },
  { key: 'reglages', label: 'Réglages' },
]

/** Coque claire, isolée du site : bandeau Veille Média + onglets + retour, pas de barre latérale. */
export function Shell({ children, user, tab, onTab, alert }: {
  children: ReactNode; user?: string; tab?: Tab; onTab?: (t: Tab) => void; alert?: ReactNode
}) {
  return (
    <div className="theme-clair relative min-h-screen flex flex-col overflow-x-hidden">
      <GuadeloupeMark className="pointer-events-none absolute -right-24 -top-12 w-[460px] h-auto hidden md:block" stroke="#1FB6A6" style={{ opacity: 0.05 }} />
      <header className="relative z-20" style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
        <div className="max-w-[1400px] mx-auto px-4 lg:px-8 py-3 flex items-center gap-3 flex-wrap">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'var(--accent-press)', boxShadow: 'var(--shadow-card)' }}>
            <span className="text-xs font-bold" style={{ color: '#fafafa' }}>VM</span>
          </div>
          <div>
            <div className={label} style={{ color: 'var(--text-muted)' }}>Veille Média Guadeloupe</div>
            <div className="text-sm font-semibold tracking-tight">Espace Publications</div>
          </div>
          {onTab && (
            <nav className="flex gap-1 sm:ml-6" aria-label="Sections">
              {TABS.map((t) => (
                <button key={t.key} type="button" onClick={() => onTab(t.key)} aria-current={tab === t.key ? 'page' : undefined}
                  className="px-3 py-2 rounded-md text-sm"
                  style={tab === t.key ? { background: 'var(--bg-elevated)', color: 'var(--text)', fontWeight: 600 } : { color: 'var(--text-secondary)' }}>
                  {t.label}
                </button>
              ))}
            </nav>
          )}
          <div className="ml-auto flex items-center gap-4 text-xs" style={{ color: 'var(--text-muted)' }}>
            {user && <span className="hidden sm:inline">{user}</span>}
            <Link href="/" className="inline-flex items-center gap-1 underline" style={{ color: 'var(--accent-link)' }}><Icon name="back" size={12} />Site de veille</Link>
          </div>
        </div>
      </header>
      {alert}
      {children}
      <footer className="relative z-10 mt-auto px-6 py-4 text-[11px] text-center" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}>
        Espace affilié à Veille Média Guadeloupe · contenu chiffré au repos · accès réservé
      </footer>
    </div>
  )
}
