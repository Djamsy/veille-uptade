'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import { type Affair } from '../../lib/api'
import { timeAgo } from '../../lib/formatters'

const API = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

interface ElectionAffair extends Affair {
  communes?: string[]
}

type SentimentKind = 'crit' | 'warn' | 'caution' | 'ok' | 'neutral'
function sentimentKind(s?: string): SentimentKind {
  const l = (s || '').toLowerCase()
  if (l.includes('critique') || l.startsWith('très négatif')) return 'crit'
  if (l.includes('négatif') || l.includes('negatif')) return 'warn'
  if (l.includes('mitigé')) return 'caution'
  if (l.includes('positif')) return 'ok'
  return 'neutral'
}

const SENT_STYLE: Record<SentimentKind, { bg: string; color: string; border: string }> = {
  crit:    { bg: 'var(--crit-soft)',   color: '#b02939', border: '#f5d4d9' },
  warn:    { bg: 'var(--warn-soft)',   color: '#9d551f', border: '#f3dcc5' },
  caution: { bg: 'var(--caution-soft)',color: '#8a7218', border: '#ecdfa9' },
  ok:      { bg: 'var(--ok-soft)',     color: '#3d6f44', border: '#cce5d0' },
  neutral: { bg: 'var(--bg-elevated)', color: 'var(--text-muted)', border: 'var(--border)' },
}

function gravityColor(pct: number): string {
  if (pct >= 70) return 'var(--negative)'
  if (pct >= 50) return 'var(--warning)'
  return 'var(--positive)'
}

export default function ElectionsPage() {
  const [elections, setElections] = useState<ElectionAffair[]>([])
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/affairs/elections`).then(r => r.json())
      setElections(res.affairs || [])
    } catch (e) {
      console.error('Elections load error:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
            Terrain / Élections
          </div>
          <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
            Élections municipales 2026
          </h1>
          <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
            Suivi des affaires liées aux municipales · <span style={{ color: 'var(--text)' }}>{elections.length}</span> affaires détectées
          </p>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1500px] mx-auto">
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="p-5" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                  <div className="skeleton h-4 w-2/3 mb-3" />
                  <div className="skeleton h-3 w-full mb-2" />
                  <div className="skeleton h-3 w-3/4" />
                </div>
              ))}
            </div>
          ) : elections.length === 0 ? (
            <div className="p-16 text-center" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Aucune affaire électorale détectée pour le moment.</p>
              <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                Les articles mentionnant les municipales 2026 créeront automatiquement des affaires.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {elections.map((affair) => {
                const gravity = Math.round((affair.gravity_score || 0) * 100)
                const sentS = SENT_STYLE[sentimentKind(affair.sentiment)]
                return (
                  <Link key={affair._id} href={`/affairs/${affair._id}`}>
                    <article
                      className="p-5 h-full transition-colors hover:bg-ink-100"
                      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <h3 className="font-serif text-[15px] font-semibold leading-snug line-clamp-2 flex-1 tracking-tight" style={{ color: 'var(--text)' }}>
                          {affair.title}
                        </h3>
                        <span
                          className="font-serif text-base font-semibold tabular-nums shrink-0"
                          style={{ color: gravityColor(gravity) }}
                        >
                          {gravity}
                        </span>
                      </div>

                      {affair.description && (
                        <p className="text-xs leading-relaxed line-clamp-3 mb-3" style={{ color: 'var(--text-secondary)' }}>
                          {affair.description}
                        </p>
                      )}

                      <div className="flex items-center gap-1.5 flex-wrap">
                        {affair.communes && affair.communes.slice(0, 3).map((c) => (
                          <span
                            key={c}
                            className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                            style={{ background: 'var(--info-soft)', color: '#2f5680', border: '1px solid #d3dde9' }}
                          >
                            {c}
                          </span>
                        ))}
                        {affair.sentiment && affair.sentiment !== 'neutre' && (
                          <span
                            className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                            style={{ background: sentS.bg, color: sentS.color, border: `1px solid ${sentS.border}` }}
                          >
                            <span className="w-1 h-1 rounded-full" style={{ background: sentS.color }} />
                            {affair.sentiment}
                          </span>
                        )}
                        <span className="font-mono text-[10px] ml-auto" style={{ color: 'var(--text-muted)' }}>
                          {affair.item_count} · {timeAgo(affair.last_activity || affair.created_at)}
                        </span>
                      </div>
                    </article>
                  </Link>
                )
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
