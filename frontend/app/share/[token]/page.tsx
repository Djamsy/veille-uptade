'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { fetchSharedAffair } from '../../../lib/api'
import { GuadeloupeMark } from '../../../components/GuadeloupeMark'
import { themeLabel } from '../../../lib/formatters'
import { gravityColor as gaugeColor, sentimentBucket, SENTIMENT_STYLE } from '../../../lib/scales'

const SENT_STYLE = SENTIMENT_STYLE
const sentimentKind = sentimentBucket

export default function SharedAffairPage() {
  const params = useParams()
  const token = params?.token as string

  const [data, setData] = useState<Awaited<ReturnType<typeof fetchSharedAffair>> | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    setLoading(true)
    fetchSharedAffair(token)
      .then(setData)
      .catch(() => setError('Lien invalide ou expiré'))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-base)' }}>
        <div className="font-mono text-xs animate-pulse" style={{ color: 'var(--text-muted)' }}>
          Chargement…
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6" style={{ background: 'var(--bg-base)' }}>
        <div
          className="p-8 max-w-md text-center elev-card"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}
        >
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--negative)' }}>
            Accès refusé
          </div>
          <h1 className="font-serif text-2xl font-medium italic mb-2 tracking-tight" style={{ color: 'var(--text)' }}>
            Lien invalide
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Ce lien de consultation n&apos;existe pas ou a été révoqué.
          </p>
        </div>
      </div>
    )
  }

  const { affair, ai_context, articles } = data
  const gravity = Math.round(affair.gravity_score * 100)
  const bmg = Math.round(affair.bmg * 100)
  const sentS = SENT_STYLE[sentimentKind(affair.sentiment)]

  return (
    <div className="relative min-h-screen overflow-hidden" style={{ background: 'var(--bg-base)', color: 'var(--text)' }}>
      {/* Signature Carte vivante — papillon en filigrane */}
      <GuadeloupeMark
        className="pointer-events-none absolute -right-24 -top-12 w-[460px] h-auto hidden md:block"
        stroke="#1FB6A6"
        style={{ opacity: 0.04 }}
      />
      {/* Header */}
      <header className="relative z-10" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="max-w-5xl mx-auto px-6 py-5">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: 'var(--brand-gradient)', boxShadow: 'var(--shadow-card)' }}
            >
              <span className="text-sm font-bold" style={{ color: 'var(--on-accent)' }}>VM</span>
            </div>
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-muted)' }}>
                Veille Média Guadeloupe
              </div>
              <div className="text-sm font-semibold tracking-tight" style={{ color: 'var(--text)' }}>
                Consultation publique
              </div>
            </div>
            <div className="flag-stripe w-12 ml-auto" />
          </div>
        </div>
      </header>

      <div className="relative z-10 max-w-5xl mx-auto px-6 py-8 space-y-5">
        {/* Title block */}
        <div
          className="p-6 elev-card"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
        >
          <div className="flex items-start gap-6 flex-wrap">
            <div className="flex-1 min-w-[280px]">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Affaire / Synthèse
              </div>
              <h2 className="font-serif text-3xl font-medium italic mb-3 tracking-tight leading-tight" style={{ color: 'var(--text)' }}>
                {affair.title}
              </h2>
              {affair.description && (
                <p className="text-sm leading-relaxed mb-4" style={{ color: 'var(--text-secondary)' }}>
                  {affair.description}
                </p>
              )}
              <div className="flex flex-wrap gap-1.5">
                <span
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                  style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                >
                  {themeLabel(affair.theme)}
                </span>
                <span
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                  style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                >
                  {affair.item_count} sources
                </span>
                {affair.sentiment && (
                  <span
                    className="inline-flex items-center gap-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                    style={{ background: sentS.bg, color: sentS.color, border: `1px solid ${sentS.border}` }}
                  >
                    <span className="w-1 h-1 rounded-full" style={{ background: sentS.color }} />
                    {affair.sentiment}
                  </span>
                )}
              </div>
            </div>

            {/* Gauges */}
            <div className="flex gap-6 shrink-0">
              <div className="text-center">
                <div className="font-serif text-4xl font-semibold tabular-nums leading-none" style={{ color: gaugeColor(gravity) }}>
                  {gravity}
                </div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] mt-1.5" style={{ color: 'var(--text-muted)' }}>
                  Gravité
                </div>
              </div>
              <div className="text-center">
                <div className="font-serif text-4xl font-semibold tabular-nums leading-none" style={{ color: gaugeColor(bmg) }}>
                  {bmg}
                </div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] mt-1.5" style={{ color: 'var(--text-muted)' }}>
                  Bruit BMG
                </div>
              </div>
            </div>
          </div>

          {(affair.elected?.length > 0 || affair.institutions?.length > 0) && (
            <div className="mt-4 pt-4 flex flex-wrap gap-1.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              {affair.elected?.map(e => (
                <span
                  key={e}
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                  style={{ background: 'var(--info-soft)', color: 'var(--accent-link)', border: '1px solid var(--border)' }}
                >
                  {e}
                </span>
              ))}
              {affair.institutions?.map(i => (
                <span
                  key={i}
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                  style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                >
                  {i}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* AI Context */}
        {ai_context && (
          <div
            className="p-6"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
          >
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
              Analyse IA
            </div>
            <h3 className="font-serif text-xl font-semibold tracking-tight mb-3" style={{ color: 'var(--text)' }}>
              Contexte
            </h3>
            <p className="font-serif text-base italic leading-relaxed mb-5" style={{ color: 'var(--text-secondary)' }}>
              {ai_context.contexte}
            </p>

            {ai_context.enjeux && ai_context.enjeux.length > 0 && (
              <Block label="Enjeux">
                <ul className="space-y-1.5">
                  {ai_context.enjeux.map((e: string, i: number) => (
                    <li key={i} className="text-sm flex items-start gap-2" style={{ color: 'var(--text-secondary)' }}>
                      <span className="mt-1.5 w-1 h-1 rounded-full shrink-0" style={{ background: 'var(--accent-press)' }} />
                      {e}
                    </li>
                  ))}
                </ul>
              </Block>
            )}

            {ai_context.historique && (
              <Block label="Historique">
                <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{ai_context.historique}</p>
              </Block>
            )}

            {ai_context.impact_potentiel && (
              <Block label="Impact potentiel">
                <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{ai_context.impact_potentiel}</p>
              </Block>
            )}

            {ai_context.mots_cles_contexte && ai_context.mots_cles_contexte.length > 0 && (
              <div className="mt-4 pt-3 flex flex-wrap gap-1" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                {ai_context.mots_cles_contexte.map((k: string, i: number) => (
                  <span
                    key={i}
                    className="font-mono text-[10px] px-1.5 py-0.5 rounded-sm"
                    style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}
                  >
                    {k}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Linked articles */}
        {articles.length > 0 && (
          <div
            className="p-6"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
          >
            <div className="flex items-baseline justify-between mb-3">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-1" style={{ color: 'var(--text-muted)' }}>
                  Sources
                </div>
                <h3 className="font-serif text-xl font-semibold tracking-tight" style={{ color: 'var(--text)' }}>
                  Articles liés
                </h3>
              </div>
              <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                {data.total_articles} au total
              </span>
            </div>
            <div className="space-y-0">
              {articles.map((art, i) => {
                const aGrav = Math.round((art.gravity_score || 0) * 100)
                const isLast = i === articles.length - 1
                return (
                  <div
                    key={art._id}
                    className="flex items-center gap-3 py-2.5"
                    style={{ borderBottom: isLast ? 'none' : '1px solid var(--border-subtle)' }}
                  >
                    <span
                      className="font-serif text-base font-semibold tabular-nums w-10 text-center shrink-0"
                      style={{ color: gaugeColor(aGrav) }}
                    >
                      {aGrav}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate" style={{ color: 'var(--text)' }}>{art.title}</div>
                      <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                        {art.source} · {themeLabel(art.theme || 'general')}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        <div className="text-center font-mono text-[10px] py-6 uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
          Veille Média Guadeloupe — Consultation en lecture seule
        </div>
      </div>
    </div>
  )
}

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--text-muted)' }}>
        {label}
      </div>
      {children}
    </div>
  )
}
