'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '../../../components/Sidebar'
import {
  fetchAffairDetail,
  recalculateBmg,
  generateAffairContext,
  fetchAffairContext,
  type Affair,
  type AffairContext,
  type TimelineEvent,
  type BmgDetails,
  type LinkedArticle,
  type LinkedRadio,
  type LinkedSocial,
} from '../../../lib/api'
import { timeAgo, themeLabel } from '../../../lib/formatters'
import { gravityColor, sentimentBucket, SENTIMENT_STYLE } from '../../../lib/scales'

const SENT_STYLE = SENTIMENT_STYLE
const sentimentKind = sentimentBucket

function formatDate(s: string): string {
  try {
    return new Date(s).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return s }
}

function CanalBar({ canal, value, max }: { canal: string; value: number; max: number }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  const colors: Record<string, string> = {
    presse: 'var(--accent-link)',
    radio: 'var(--warning)',
    tv: 'var(--negative)',
    social: 'var(--positive)',
  }
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="capitalize w-14" style={{ color: 'var(--text-muted)' }}>{canal}</span>
      <div className="flex-1 h-1.5 rounded-sm" style={{ background: 'var(--bg-elevated)' }}>
        <div
          className="h-full rounded-sm transition-all duration-500"
          style={{ width: `${Math.max(pct, 2)}%`, background: colors[canal] || 'var(--text-muted)' }}
        />
      </div>
      <span className="font-mono tabular-nums w-10 text-right" style={{ color: 'var(--text-secondary)' }}>{value.toFixed(1)}</span>
    </div>
  )
}

export default function AffairDetailPage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()

  const [affair, setAffair] = useState<Affair | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [bmgLive, setBmgLive] = useState<BmgDetails | null>(null)
  const [articles, setArticles] = useState<LinkedArticle[]>([])
  const [radio, setRadio] = useState<LinkedRadio[]>([])
  const [social, setSocial] = useState<LinkedSocial[]>([])
  const [ctx, setCtx] = useState<AffairContext | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchAffairDetail(id)
      setAffair(data.affair)
      setTimeline(data.timeline || [])
      setBmgLive(data.bmg_live)
      setArticles(data.linked_articles || [])
      setRadio(data.linked_radio || [])
      setSocial(data.linked_social || [])
      try {
        const c = await fetchAffairContext(id)
        setCtx(c)
      } catch { /* ignore */ }
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const handleRecalcBmg = async () => {
    setBusy('bmg')
    try { await recalculateBmg(id); await load() }
    catch (e) { console.error(e) }
    finally { setBusy('') }
  }

  const handleGenerateCtx = async () => {
    setBusy('ctx')
    try { await generateAffairContext(id); await load() }
    catch (e) { console.error(e) }
    finally { setBusy('') }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
        <Sidebar />
        <main className="lg:ml-16 flex-1 p-8 font-mono text-xs animate-pulse" style={{ color: 'var(--text-muted)' }}>
          Chargement…
        </main>
      </div>
    )
  }

  if (error || !affair) {
    return (
      <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
        <Sidebar />
        <main className="lg:ml-16 flex-1 p-8">
          <div className="max-w-xl">
            <Link href="/affairs" className="inline-flex items-center gap-1 text-xs font-mono mb-4" style={{ color: 'var(--accent-link)' }}>
              ← Affaires
            </Link>
            <div
              className="px-4 py-3 text-xs"
              style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}
            >
              {error || 'Affaire introuvable'}
            </div>
          </div>
        </main>
      </div>
    )
  }

  const gravity = Math.round(affair.gravity_score * 100)
  const bmg = Math.round(affair.bmg * 100)
  const bmgValues = bmgLive ? Object.values(bmgLive.bnp_by_canal) : []
  const maxCanal = Math.max(...bmgValues, 1)
  const sentS = SENT_STYLE[sentimentKind(affair.sentiment)]

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <Link
            href="/affairs"
            className="inline-flex items-center gap-1 text-xs font-mono mb-3 hover:underline"
            style={{ color: 'var(--accent-link)' }}
          >
            ← Affaires
          </Link>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex-1 min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Affaire / Détail · {themeLabel(affair.theme)}
              </div>
              <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic leading-[1.1]" style={{ color: 'var(--text)' }}>
                {affair.title || affair.primary_entity || 'Affaire'}
              </h1>
              {affair.description && (
                <p className="mt-3 text-sm leading-relaxed max-w-3xl" style={{ color: 'var(--text-secondary)' }}>
                  {affair.description}
                </p>
              )}
            </div>
            <div className="flex flex-col items-end gap-2 shrink-0">
              <div className="flex gap-4">
                <div className="text-center">
                  <div className="font-serif text-4xl font-semibold tabular-nums leading-none" style={{ color: gravityColor(gravity) }}>
                    {gravity}
                  </div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.14em] mt-1" style={{ color: 'var(--text-muted)' }}>
                    Gravité
                  </div>
                </div>
                <div className="text-center">
                  <div className="font-serif text-4xl font-semibold tabular-nums leading-none" style={{ color: gravityColor(bmg) }}>
                    {bmg}
                  </div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.14em] mt-1" style={{ color: 'var(--text-muted)' }}>
                    BMG
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleRecalcBmg}
                  disabled={busy === 'bmg'}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-sm transition-colors hover:bg-ink-100 disabled:opacity-50"
                  style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
                >
                  {busy === 'bmg' ? 'Calcul…' : 'Recalculer BMG'}
                </button>
                <button
                  onClick={handleGenerateCtx}
                  disabled={busy === 'ctx'}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold rounded-sm transition-colors disabled:opacity-50"
                  style={{ background: 'var(--accent-press)', color: '#fafafa', border: '1px solid var(--accent-press)' }}
                >
                  {busy === 'ctx' ? 'Génération…' : 'Analyse IA'}
                </button>
              </div>
            </div>
          </div>

          {/* Meta chips */}
          <div className="flex flex-wrap gap-1.5 mt-4">
            {affair.sentiment && (
              <span
                className="inline-flex items-center gap-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                style={{ background: sentS.bg, color: sentS.color, border: `1px solid ${sentS.border}` }}
              >
                <span className="w-1 h-1 rounded-full" style={{ background: sentS.color }} />
                {affair.sentiment}
              </span>
            )}
            <span
              className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm font-mono"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            >
              {affair.item_count} items
            </span>
            <span
              className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm font-mono"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            >
              {(affair.sources || []).length} sources
            </span>
            {affair.elected?.map(e => (
              <span
                key={e}
                className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                style={{ background: 'var(--info-soft)', color: '#2f5680', border: '1px solid #d3dde9' }}
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
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1500px] mx-auto grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5">
          <section className="flex flex-col gap-5 min-w-0">
            {ctx && (
              <Section label="Analyse IA">
                <p className="font-serif text-base italic leading-relaxed mb-4" style={{ color: 'var(--text-secondary)' }}>
                  {ctx.contexte}
                </p>
                {ctx.enjeux?.length > 0 && (
                  <Block label="Enjeux">
                    <ul className="space-y-1.5">
                      {ctx.enjeux.map((e, i) => (
                        <li key={i} className="text-sm flex items-start gap-2" style={{ color: 'var(--text-secondary)' }}>
                          <span className="mt-1.5 w-1 h-1 rounded-full shrink-0" style={{ background: 'var(--accent-press)' }} />
                          {e}
                        </li>
                      ))}
                    </ul>
                  </Block>
                )}
                {ctx.historique && (
                  <Block label="Historique">
                    <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{ctx.historique}</p>
                  </Block>
                )}
                {ctx.impact_potentiel && (
                  <Block label="Impact potentiel">
                    <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{ctx.impact_potentiel}</p>
                  </Block>
                )}
                {ctx.mots_cles_contexte?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-4 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    {ctx.mots_cles_contexte.map((k, i) => (
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
              </Section>
            )}

            {articles.length > 0 && (
              <Section label="Articles" count={articles.length}>
                <div className="space-y-0">
                  {articles.map((a, i) => {
                    const g = Math.round((a.gravity_score || 0) * 100)
                    return (
                      <div
                        key={a._id}
                        className="flex items-start gap-3 py-2.5"
                        style={{ borderBottom: i < articles.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}
                      >
                        <span
                          className="font-serif text-base font-semibold tabular-nums w-10 text-center shrink-0"
                          style={{ color: gravityColor(g) }}
                        >
                          {g}
                        </span>
                        <div className="flex-1 min-w-0">
                          <a
                            href={a.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-medium hover:underline"
                            style={{ color: 'var(--text)' }}
                          >
                            {a.title}
                          </a>
                          <div className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                            {a.source} · {timeAgo(a.date || a.scraped_at || '')}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </Section>
            )}

            {radio.length > 0 && (
              <Section label="Radio" count={radio.length}>
                <div className="space-y-2.5">
                  {radio.map(r => (
                    <div key={r._id} className="py-1.5">
                      <div className="flex items-baseline gap-2 mb-0.5">
                        <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>{r.topic_title || r.radio}</span>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{r.radio}</span>
                        <span className="ml-auto font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                          {timeAgo(r.captured_at || '')}
                        </span>
                      </div>
                      <p className="text-xs leading-relaxed line-clamp-3" style={{ color: 'var(--text-secondary)' }}>
                        {r.topic_summary || r.summary || r.text}
                      </p>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {social.length > 0 && (
              <Section label="Réseaux sociaux" count={social.length}>
                <div className="space-y-2.5">
                  {social.map(s => (
                    <div key={s._id} className="py-1.5">
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className="font-mono text-[10px] uppercase tracking-[0.12em] px-1.5 py-0.5 rounded-sm"
                          style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                        >
                          {s.platform}
                        </span>
                        {s.author && <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{s.author}</span>}
                        <span className="ml-auto font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                          {timeAgo(s.created_at || '')}
                        </span>
                      </div>
                      <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{s.text}</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </section>

          <aside className="flex flex-col gap-5 min-w-0">
            {bmgLive && (
              <Section label="BMG par canal">
                <div className="space-y-2">
                  {Object.entries(bmgLive.bnp_by_canal).map(([canal, v]) => (
                    <CanalBar key={canal} canal={canal} value={v} max={maxCanal} />
                  ))}
                </div>
                <div className="mt-3 pt-3 grid grid-cols-2 gap-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <Mini label="Canaux actifs" value={String(bmgLive.active_canals)} />
                  <Mini label="Dominant" value={bmgLive.dominant_canal || '—'} />
                  <Mini label="Niveau" value={bmgLive.niveau_alerte} />
                  <Mini label="Items" value={String(bmgLive.total_items)} />
                </div>
              </Section>
            )}

            {timeline.length > 0 && (
              <Section label="Chronologie" count={timeline.length}>
                <div className="space-y-3">
                  {timeline.slice(0, 8).map(ev => (
                    <div key={ev._id} className="flex gap-2.5">
                      <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ background: 'var(--accent-press)' }} />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium" style={{ color: 'var(--text)' }}>
                          {ev.event.replace(/_/g, ' ')}
                        </div>
                        <div className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                          {formatDate(ev.timestamp)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            <button
              onClick={() => router.back()}
              className="text-xs font-mono hover:underline self-start"
              style={{ color: 'var(--text-muted)' }}
            >
              ← Retour
            </button>
          </aside>
        </div>
      </main>
    </div>
  )
}

function Section({ label, count, children }: { label: string; count?: number; children: React.ReactNode }) {
  return (
    <section style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
      <div className="flex items-baseline justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>{label}</span>
        {count != null && <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{count}</span>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--text-muted)' }}>{label}</div>
      {children}
    </div>
  )
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[9px] uppercase tracking-[0.12em]" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-xs font-medium mt-0.5 capitalize" style={{ color: 'var(--text)' }}>{value}</div>
    </div>
  )
}
