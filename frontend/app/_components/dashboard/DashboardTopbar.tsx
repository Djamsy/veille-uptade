'use client'

import { useState, useEffect } from 'react'

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
      className="px-6 lg:px-8 pt-5 pb-5"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <span
              className="font-mono text-[10px] uppercase tracking-[0.18em]"
              style={{ color: 'var(--text-muted)' }}
            >
              Pilotage / Vue d&rsquo;ensemble
            </span>
          </div>
          <h1
            className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic"
            style={{ color: 'var(--text)' }}
          >
            Édition du {formatDateLong(lastRefresh)}
          </h1>
          <div className="flex items-center gap-3 mt-2.5 font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
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

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={onOpenBrief}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-press"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2M9 12h6m-6 4h6" />
            </svg>
            Brief du jour
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
            {refreshing ? 'Actualisation…' : 'Actualiser'}
          </button>
          <button
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-press"
            style={{ background: 'var(--accent-press)', color: '#fafafa', border: '1px solid var(--accent-press)' }}
            onClick={() => window.print()}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v12m0 0l4-4m-4 4l-4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
            </svg>
            Export PDF
          </button>
        </div>
      </div>
    </header>
  )
}
