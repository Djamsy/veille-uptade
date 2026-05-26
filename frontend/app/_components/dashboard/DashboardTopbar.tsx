'use client'

import { useState, useEffect } from 'react'
import { GuadeloupeMark } from '../../../components/GuadeloupeMark'

type Props = {
  lastRefresh: Date
  onRefresh: () => void | Promise<void>
  onOpenBrief: () => void
  refreshing?: boolean
  cycleId?: number | string
}

function formatDateLong(d: Date): string {
  const day = d.toLocaleDateString('fr-FR', { day: 'numeric' })
  const month = d.toLocaleDateString('fr-FR', { month: 'long' })
  return `${day} ${month}`
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

export function DashboardTopbar({ lastRefresh, onRefresh, onOpenBrief, refreshing, cycleId }: Props) {
  const [now, setNow] = useState<Date | null>(null)
  useEffect(() => {
    setNow(new Date())
    const t = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(t)
  }, [])

  return (
    <header
      className="relative px-6 lg:px-8 pt-5 pb-5"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      {/* Watermark clippé dans SON propre conteneur — ne peut jamais rogner le titre.
         (le header n'a plus overflow-hidden, donc la masthead ne sera jamais coupée) */}
      <div className="hidden lg:block absolute inset-0 overflow-hidden pointer-events-none" aria-hidden>
        <GuadeloupeMark
          className="absolute -right-6 bottom-0 w-[300px] h-auto"
          stroke="#1FB6A6"
          style={{ opacity: 0.05 }}
        />
      </div>
      <div className="relative">
        {/* Barre utilitaire : indicatif à gauche, actions à droite — libère la masthead */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-2 reveal reveal-1">
            <span
              className="font-mono text-[11px] uppercase tracking-[0.2em] font-semibold"
              style={{ color: 'var(--text)' }}
              aria-label="Indicatif Guadeloupe"
            >
              971
            </span>
            <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>·</span>
            <span
              className="font-mono text-[11px] uppercase tracking-[0.2em]"
              style={{ color: 'var(--text-muted)' }}
            >
              Pilotage · Vue d&rsquo;ensemble
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0 reveal reveal-1">
            <button
              onClick={onOpenBrief}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-press"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2M9 12h6m-6 4h6" />
              </svg>
              <span className="hidden sm:inline">Brief du jour</span>
            </button>
            <button
              onClick={onRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-press disabled:opacity-50"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
            >
              <svg className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 12a9 9 0 0115.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 01-15.5 6.3L3 16M3 21v-5h5" />
              </svg>
              <span className="hidden sm:inline">{refreshing ? 'Actualisation…' : 'Actualiser'}</span>
            </button>
            <button
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-press"
              style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}
              onClick={() => window.print()}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v12m0 0l4-4m-4 4l-4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
              </svg>
              <span className="hidden sm:inline">Export PDF</span>
            </button>
          </div>
        </div>

        <h1
          className="masthead text-4xl sm:text-5xl lg:text-6xl font-medium reveal reveal-2"
          style={{ color: 'var(--text)' }}
        >
          Édition du {formatDateLong(lastRefresh)}
        </h1>
        {/* Signature 971 — drapeau GP éditorialisé, marqueur d'identité délibéré */}
        <div className="flag-stripe w-24 mt-3.5 reveal reveal-2" />
        <div className="flex items-center gap-3 mt-3 font-mono text-xs reveal reveal-3" style={{ color: 'var(--text-muted)' }}>
          <span>{now ? formatTime(now) : '--:--'} GMT-4</span>
          <span aria-hidden>·</span>
          <span>cycle #{cycleId ?? '—'}</span>
          <span aria-hidden>·</span>
          <span className="inline-flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: 'var(--positive)' }}
            />
            <span style={{ color: 'var(--positive)' }}>LIVE</span>
          </span>
        </div>
      </div>
    </header>
  )
}
