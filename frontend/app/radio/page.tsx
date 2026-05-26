'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchRadioCardsToday,
  fetchRadioCards,
  captureRadioNow,
  type RadioCard,
} from '../../lib/api'
import { timeAgo } from '../../lib/formatters'

function sourceAccent(source?: string): string {
  if (!source) return 'var(--text-muted)'
  const s = source.toLowerCase()
  if (s.includes('rci')) return 'var(--negative)'
  if (s.includes('1ère') || s.includes('guadeloupe') || s.includes('gp')) return 'var(--accent-link)'
  if (s.includes('karib')) return 'var(--positive)'
  return 'var(--text-muted)'
}

function RadioCardItem({ card, expanded, onToggle }: { card: RadioCard; expanded: boolean; onToggle: () => void }) {
  const accent = sourceAccent(card.source)
  const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
  const audioSrc = card.audioUrl
    ? (card.audioUrl.startsWith('http') ? card.audioUrl : `${BACKEND_URL}${card.audioUrl}`)
    : null

  return (
    <article
      className="relative overflow-hidden"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
      }}
    >
      <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: accent, opacity: 0.7 }} />

      <div className="pl-[18px] pr-4 pt-4 pb-3">
        <div className="flex items-start gap-3 mb-2 flex-wrap">
          <span
            className="inline-flex items-center gap-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
            style={{
              background: 'var(--bg-elevated)',
              color: accent,
              border: `1px solid ${accent}40`,
            }}
          >
            <span className="w-1 h-1 rounded-full" style={{ background: accent }} />
            {card.source || 'Radio'}
          </span>
          <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {card.capturedAt ? new Date(card.capturedAt).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : '—'}
          </span>
          <span className="ml-auto font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {timeAgo(card.capturedAt || '')}
          </span>
        </div>
        <h3 className="font-serif text-[15px] font-semibold leading-snug tracking-tight" style={{ color: 'var(--text)' }}>
          {card.title}
        </h3>
        {card.subtitle && (
          <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{card.subtitle}</p>
        )}
      </div>

      {card.summary && (
        <div className="pl-[18px] pr-4 pb-3">
          <div className="inline-flex items-center gap-1.5 mb-2">
            <span
              className="font-mono text-[10px] uppercase tracking-[0.12em] px-1.5 py-0.5 rounded-sm"
              style={{
                background: card.summarySource === 'gpt' ? 'var(--ok-soft)' : 'var(--bg-elevated)',
                color: card.summarySource === 'gpt' ? '#3d6f44' : 'var(--text-muted)',
                border: `1px solid ${card.summarySource === 'gpt' ? '#cce5d0' : 'var(--border)'}`,
              }}
            >
              {card.summarySource === 'gpt' ? 'Résumé IA' : 'Transcription'}
            </span>
          </div>
          <p
            className={`text-[13px] leading-relaxed ${expanded ? '' : 'line-clamp-3'}`}
            style={{ color: 'var(--text-secondary)' }}
          >
            {expanded && card.fullSummary ? card.fullSummary : card.summary}
          </p>
          {card.isTruncated && (
            <button
              onClick={onToggle}
              className="mt-2 text-[11px] font-medium hover:underline"
              style={{ color: 'var(--accent-link)' }}
            >
              {expanded ? '▴ Réduire' : '▾ Voir tout'}
            </button>
          )}
        </div>
      )}

      {audioSrc && (
        <div
          className="pl-[18px] pr-4 py-3"
          style={{ borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-elevated)' }}
        >
          <audio controls src={audioSrc} className="w-full h-8" style={{ outline: 'none' }} preload="none" />
        </div>
      )}
    </article>
  )
}

export default function RadioPage() {
  const [cards, setCards] = useState<RadioCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<'today' | 'date'>('today')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [capturing, setCapturing] = useState(false)
  const [sourceFilter, setSourceFilter] = useState<'all' | 'rci' | 'gp1'>('all')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = mode === 'today'
        ? await fetchRadioCardsToday(30)
        : await fetchRadioCards(date, 50)
      setCards(data.cards || [])
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }, [mode, date])

  useEffect(() => { load() }, [load])

  const handleCapture = async () => {
    setCapturing(true)
    try {
      await captureRadioNow('', 60)
      setTimeout(load, 2000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Capture failed')
    } finally {
      setCapturing(false)
    }
  }

  const filtered = cards.filter(c => {
    if (sourceFilter === 'all') return true
    const s = (c.source || '').toLowerCase()
    if (sourceFilter === 'rci') return s.includes('rci')
    if (sourceFilter === 'gp1') return s.includes('1ère') || s.includes('guadeloupe')
    return true
  })

  const todayCount = cards.length
  const transcribed = cards.filter(c => c.summarySource === 'gpt' && c.summary).length
  const errored = cards.filter(c => !c.summary).length

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Pilotage / Radio
              </div>
              <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
                Transcriptions radio
              </h1>
              <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                <span style={{ color: 'var(--text)' }}>{todayCount}</span> transcription{todayCount > 1 ? 's' : ''} ·{' '}
                {mode === 'today' ? "Aujourd'hui" : new Date(date).toLocaleDateString('fr-FR', { dateStyle: 'long' })}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <div className="inline-flex" style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
                <button
                  onClick={() => setMode('today')}
                  className="px-3 py-1.5 text-xs font-medium"
                  style={{
                    background: mode === 'today' ? 'var(--bg-hover)' : 'var(--bg-surface)',
                    color: mode === 'today' ? 'var(--text)' : 'var(--text-muted)',
                  }}
                >
                  Aujourd&apos;hui
                </button>
                <button
                  onClick={() => setMode('date')}
                  className="px-3 py-1.5 text-xs font-medium"
                  style={{
                    background: mode === 'date' ? 'var(--bg-hover)' : 'var(--bg-surface)',
                    color: mode === 'date' ? 'var(--text)' : 'var(--text-muted)',
                    borderLeft: '1px solid var(--border)',
                  }}
                >
                  Par date
                </button>
              </div>
              {mode === 'date' && (
                <input
                  type="date"
                  value={date}
                  onChange={e => setDate(e.target.value)}
                  className="px-2 py-1.5 text-xs"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 'var(--radius-sm)' }}
                />
              )}
              <button
                onClick={handleCapture}
                disabled={capturing}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-sm transition-colors disabled:opacity-50"
                style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
                  <rect x="9" y="3" width="6" height="12" rx="3" />
                  <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                </svg>
                {capturing ? 'Capture…' : 'Capturer'}
              </button>
            </div>
          </div>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1500px] mx-auto space-y-5">
          {/* Stat strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-4" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--text-muted)' }}>Captures aujourd&apos;hui</div>
              <div className="flex items-baseline gap-2">
                <span className="font-serif text-3xl font-semibold tabular-nums" style={{ color: 'var(--text)' }}>{todayCount}</span>
                <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>/ 12 prévues</span>
              </div>
            </div>
            <div className="p-4" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--text-muted)' }}>Transcrites</div>
              <span className="font-serif text-3xl font-semibold tabular-nums" style={{ color: 'var(--positive)' }}>{transcribed}</span>
            </div>
            <div className="p-4" style={{ background: 'var(--bg-surface)', border: `1px solid ${errored > 0 ? '#f5d4d9' : 'var(--border)'}`, borderRadius: 'var(--radius)' }}>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: errored > 0 ? 'var(--negative)' : 'var(--text-muted)' }}>En attente</div>
              <span className="font-serif text-3xl font-semibold tabular-nums" style={{ color: errored > 0 ? 'var(--negative)' : 'var(--text)' }}>{errored}</span>
            </div>
            <div className="p-4" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--text-muted)' }}>Sources actives</div>
              <span className="font-serif text-3xl font-semibold tabular-nums" style={{ color: 'var(--text)' }}>
                {new Set(cards.map(c => c.source).filter(Boolean)).size}
              </span>
            </div>
          </div>

          {/* Source filter chips */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] mr-1" style={{ color: 'var(--text-muted)' }}>
              Source
            </span>
            {[
              { v: 'all', label: 'Toutes', count: cards.length },
              { v: 'rci', label: 'RCI', count: cards.filter(c => (c.source || '').toLowerCase().includes('rci')).length },
              { v: 'gp1', label: 'Guadeloupe 1ère', count: cards.filter(c => { const s = (c.source || '').toLowerCase(); return s.includes('1ère') || s.includes('guadeloupe') }).length },
            ].map(opt => (
              <button
                key={opt.v}
                onClick={() => setSourceFilter(opt.v as 'all' | 'rci' | 'gp1')}
                className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-full"
                style={{
                  background: sourceFilter === opt.v ? 'var(--accent-press)' : 'var(--bg-surface)',
                  color: sourceFilter === opt.v ? 'var(--on-accent)' : 'var(--text-secondary)',
                  border: `1px solid ${sourceFilter === opt.v ? 'var(--accent-press)' : 'var(--border)'}`,
                }}
              >
                {opt.label} <span style={{ color: sourceFilter === opt.v ? 'rgba(250,250,250,0.6)' : 'var(--text-muted)' }}>{opt.count}</span>
              </button>
            ))}
          </div>

          {error && (
            <div className="px-4 py-3 text-xs" style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}>
              {error}
            </div>
          )}

          {loading ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="p-5" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                  <div className="skeleton h-4 w-2/3 mb-3" />
                  <div className="skeleton h-3 w-full mb-2" />
                  <div className="skeleton h-3 w-5/6 mb-2" />
                  <div className="skeleton h-3 w-2/3" />
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-16 text-center" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Aucune transcription</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {filtered.map(card => (
                <RadioCardItem
                  key={card.id}
                  card={card}
                  expanded={!!expanded[card.id]}
                  onToggle={() => setExpanded(prev => ({ ...prev, [card.id]: !prev[card.id] }))}
                />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
