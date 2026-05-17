'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import {
  fetchBriefing,
  sendBriefingTelegram,
  fetchTrending,
  fetchWatchlist,
  addWatchlistKeyword,
  removeWatchlistKeyword,
  type BriefingResponse,
  type TrendingAffair,
  type WatchlistItem,
  type BriefingAffair,
  type RadioHighlight,
  type WatchlistHit,
  type CoverageGap,
} from '@/lib/api'
import { themeLabel, timeAgo } from '../../lib/formatters'

function gravityColor(g: number): string {
  if (g >= 0.75) return 'var(--negative)'
  if (g >= 0.55) return 'var(--warning)'
  if (g >= 0.4) return 'var(--caution)'
  return 'var(--positive)'
}

function gravityLabel(g: number): string {
  if (g >= 0.75) return 'CRITIQUE'
  if (g >= 0.55) return 'IMPORTANT'
  if (g >= 0.4) return 'À SUIVRE'
  return 'MINEUR'
}

export default function BriefingPage() {
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null)
  const [trending, setTrending] = useState<TrendingAffair[]>([])
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [hours, setHours] = useState(24)
  const [newKeyword, setNewKeyword] = useState('')
  const [newCategory, setNewCategory] = useState('general')
  const [telegramSending, setTelegramSending] = useState(false)
  const [telegramMsg, setTelegramMsg] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [bRes, tRes, wRes] = await Promise.all([
        fetchBriefing(hours),
        fetchTrending(12),
        fetchWatchlist(),
      ])
      setBriefing(bRes)
      setTrending(tRes.trending || [])
      setWatchlist(wRes.watchlist || [])
    } catch (e: unknown) {
      setError((e as Error).message || 'Erreur chargement')
    } finally {
      setLoading(false)
    }
  }, [hours])

  useEffect(() => { loadData() }, [loadData])

  const handleSendTelegram = async () => {
    setTelegramSending(true)
    try {
      const res = await sendBriefingTelegram(hours)
      setTelegramMsg(res.message || 'Envoyé')
      setTimeout(() => setTelegramMsg(''), 3000)
    } catch {
      setTelegramMsg('Erreur envoi')
    } finally {
      setTelegramSending(false)
    }
  }

  const handleAddKeyword = async () => {
    if (!newKeyword.trim()) return
    try {
      await addWatchlistKeyword(newKeyword.trim(), newCategory)
      setNewKeyword('')
      const wRes = await fetchWatchlist()
      setWatchlist(wRes.watchlist || [])
    } catch { /* ignore */ }
  }

  const handleRemoveKeyword = async (id: string) => {
    try {
      await removeWatchlistKeyword(id)
      const wRes = await fetchWatchlist()
      setWatchlist(wRes.watchlist || [])
    } catch { /* ignore */ }
  }

  const b = briefing?.briefing
  const stats = b?.stats

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Analyse / Briefing
              </div>
              <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
                Briefing
              </h1>
              <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                Période <span style={{ color: 'var(--text)' }}>{hours}h</span> ·{' '}
                {b ? `généré ${timeAgo(b.generated_at)}` : 'en attente'}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <div className="inline-flex" style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
                {[24, 48, 72].map((h, i) => (
                  <button
                    key={h}
                    onClick={() => setHours(h)}
                    className="px-3 py-1.5 text-xs font-medium"
                    style={{
                      background: hours === h ? 'var(--bg-hover)' : 'var(--bg-surface)',
                      color: hours === h ? 'var(--text)' : 'var(--text-muted)',
                      borderLeft: i > 0 ? '1px solid var(--border)' : 'none',
                    }}
                  >
                    {h}h
                  </button>
                ))}
              </div>
              <button
                onClick={loadData}
                disabled={loading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              >
                <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 12a9 9 0 0115.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 01-15.5 6.3L3 16M3 21v-5h5" />
                </svg>
                Actualiser
              </button>
              <button
                onClick={handleSendTelegram}
                disabled={telegramSending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-sm transition-colors disabled:opacity-50"
                style={{ background: 'var(--accent-press)', color: '#fafafa', border: '1px solid var(--accent-press)' }}
              >
                {telegramSending ? 'Envoi…' : telegramMsg || 'Envoyer Telegram'}
              </button>
            </div>
          </div>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1700px] mx-auto grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5">
          <section className="flex flex-col gap-5 min-w-0">
            {error && (
              <div
                className="px-4 py-3 text-xs"
                style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}
              >
                {error}
              </div>
            )}

            {/* Stats strip */}
            {stats && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Kpi label="Affaires actives" value={stats.total_active_affairs} />
                <Kpi label="Nouvelles" value={stats.new_affairs_count} severity={stats.new_affairs_count > 0 ? 'crit' : 'neutral'} />
                <Kpi label={`Articles · ${hours}h`} value={stats.articles_count} />
                <Kpi label={`Captures radio · ${hours}h`} value={stats.radio_captures_count} />
              </div>
            )}

            {/* Top affairs */}
            {b && (
              <BlockSection label="Top affaires" count={b.top_affairs?.length || 0} loading={loading}>
                {b.top_affairs?.slice(0, 6).map(a => <BriefingAffairRow key={a._id} a={a} />)}
              </BlockSection>
            )}

            {/* New affairs */}
            {b && b.new_affairs?.length > 0 && (
              <BlockSection label="Nouvelles affaires" count={b.new_affairs.length} loading={false}>
                {b.new_affairs.slice(0, 6).map(a => <BriefingAffairRow key={a._id} a={a} />)}
              </BlockSection>
            )}

            {/* Radio highlights */}
            {b && b.radio_highlights?.length > 0 && (
              <BlockSection label="Faits radio" count={b.radio_highlights.length} loading={false}>
                <div className="space-y-2">
                  {b.radio_highlights.slice(0, 5).map((r, i) => <RadioRow key={i} r={r} />)}
                </div>
              </BlockSection>
            )}

            {/* Coverage gaps */}
            {b && b.coverage?.coverage_gaps?.length > 0 && (
              <BlockSection label="Lacunes de couverture" count={b.coverage.coverage_gaps.length} loading={false}>
                <div className="space-y-2">
                  {b.coverage.coverage_gaps.slice(0, 5).map((c, i) => <GapRow key={i} g={c} />)}
                </div>
              </BlockSection>
            )}
          </section>

          {/* Right rail */}
          <aside className="flex flex-col gap-5 min-w-0">
            {trending.length > 0 && (
              <Panel label="Tendances">
                <div className="space-y-2">
                  {trending.slice(0, 6).map(t => (
                    <Link key={t._id} href={`/affairs/${t._id}`}>
                      <div className="flex items-start gap-2.5 py-1.5 transition-colors hover:bg-ink-100 px-2 -mx-2 rounded-sm">
                        <span
                          className="font-serif text-base font-semibold tabular-nums w-8 text-center shrink-0"
                          style={{ color: gravityColor(t.gravity_score) }}
                        >
                          {Math.round(t.gravity_score * 100)}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium truncate" style={{ color: 'var(--text)' }}>{t.title}</div>
                          <div className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                            {themeLabel(t.theme)} · vélocité {Math.round(t.velocity * 10) / 10}
                            {t.is_new && <span className="ml-1" style={{ color: 'var(--negative)' }}>· NEW</span>}
                          </div>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </Panel>
            )}

            {/* Watchlist */}
            <Panel label="Watchlist">
              <div className="space-y-2">
                {watchlist.map(item => (
                  <div key={item._id} className="flex items-center gap-2 group">
                    <span className="flex-1 text-xs" style={{ color: 'var(--text)' }}>
                      <span className="font-medium">{item.keyword_display}</span>
                      {item.hit_count > 0 && (
                        <span className="font-mono ml-1.5" style={{ color: 'var(--text-muted)' }}>
                          ({item.hit_count})
                        </span>
                      )}
                    </span>
                    <button
                      onClick={() => handleRemoveKeyword(item._id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px]"
                      style={{ color: 'var(--text-muted)' }}
                      aria-label="Retirer"
                    >
                      ✕
                    </button>
                  </div>
                ))}
                {watchlist.length === 0 && (
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Aucun mot-clé suivi</p>
                )}
              </div>
              <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <div className="flex gap-1.5">
                  <input
                    value={newKeyword}
                    onChange={e => setNewKeyword(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAddKeyword()}
                    placeholder="Mot-clé…"
                    className="flex-1 min-w-0 px-2 py-1 text-xs focus:outline-none"
                    style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)' }}
                  />
                  <select
                    value={newCategory}
                    onChange={e => setNewCategory(e.target.value)}
                    className="text-xs px-1.5 py-1 cursor-pointer"
                    style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)' }}
                  >
                    <option value="general">Général</option>
                    <option value="politique">Politique</option>
                    <option value="economie">Économie</option>
                    <option value="securite">Sécurité</option>
                  </select>
                  <button
                    onClick={handleAddKeyword}
                    className="px-2 py-1 text-xs font-semibold rounded-sm"
                    style={{ background: 'var(--accent-press)', color: '#fafafa' }}
                  >
                    +
                  </button>
                </div>
              </div>
            </Panel>

            {/* Watchlist hits */}
            {b && b.watchlist_hits?.length > 0 && (
              <Panel label="Hits watchlist">
                <div className="space-y-1.5">
                  {b.watchlist_hits.slice(0, 6).map((h, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <span className="font-medium" style={{ color: 'var(--text)' }}>{h.keyword}</span>
                      <span className="ml-auto font-mono" style={{ color: 'var(--text-muted)' }}>
                        {h.articles_matched + h.radio_matched}
                      </span>
                    </div>
                  ))}
                </div>
              </Panel>
            )}
          </aside>
        </div>
      </main>
    </div>
  )
}

function Panel({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
      <div className="px-3.5 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
          {label}
        </span>
      </div>
      <div className="p-3.5">{children}</div>
    </div>
  )
}

function BlockSection({ label, count, loading, children }: { label: string; count: number; loading: boolean; children: React.ReactNode }) {
  return (
    <section style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
      <div className="flex items-baseline justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{count}</span>
      </div>
      <div className="px-4 py-2">
        {loading ? <p className="text-xs py-3 text-center" style={{ color: 'var(--text-muted)' }}>Chargement…</p> : children}
      </div>
    </section>
  )
}

function BriefingAffairRow({ a }: { a: BriefingAffair }) {
  const g = a.gravity_score
  const c = gravityColor(g)
  const bmg = Math.round((a.bmg ?? g) * 100)
  return (
    <Link href={`/affairs/${a._id}`}>
      <div className="flex items-center gap-3 py-2.5 transition-colors hover:bg-ink-100 px-2 -mx-2 rounded-sm">
        <div className="flex flex-col items-center shrink-0 w-12">
          <span className="font-serif text-lg font-semibold tabular-nums leading-none" style={{ color: c }}>{bmg}</span>
          <span className="font-mono text-[8px] uppercase tracking-[0.1em] mt-1" style={{ color: c }}>{gravityLabel(g)}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium" style={{ color: 'var(--text)' }}>{a.title}</div>
          <div className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {themeLabel(a.theme)} · {a.item_count} items · {a.sources?.length || 0} src · {timeAgo(a.last_activity || a.created_at)}
          </div>
        </div>
      </div>
    </Link>
  )
}

function RadioRow({ r }: { r: RadioHighlight }) {
  return (
    <div className="flex gap-3 py-2">
      <span
        className="font-serif text-base font-semibold tabular-nums w-10 text-center shrink-0"
        style={{ color: gravityColor(r.gravity) }}
      >
        {Math.round(r.gravity * 100)}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium mb-0.5" style={{ color: 'var(--text)' }}>{r.topic || r.stream}</div>
        <p className="text-xs line-clamp-2 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{r.summary}</p>
        <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
          {r.stream} · {timeAgo(r.captured_at)}
        </div>
      </div>
    </div>
  )
}

function GapRow({ g }: { g: CoverageGap }) {
  return (
    <div className="py-2">
      <div className="text-sm font-medium mb-1" style={{ color: 'var(--text)' }}>{g.affair_title}</div>
      <div className="flex gap-1.5 flex-wrap">
        {g.missing_from.map(src => (
          <span
            key={src}
            className="font-mono text-[10px] px-1.5 py-0.5 rounded-sm"
            style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9' }}
          >
            absent : {src}
          </span>
        ))}
      </div>
    </div>
  )
}

function Kpi({ label, value, severity }: { label: string; value: number; severity?: 'crit' | 'warn' | 'ok' | 'neutral' }) {
  const isCrit = severity === 'crit'
  return (
    <div
      className="p-4"
      style={{ background: 'var(--bg-surface)', border: `1px solid ${isCrit ? '#f5d4d9' : 'var(--border)'}`, borderRadius: 'var(--radius)' }}
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: isCrit ? 'var(--negative)' : 'var(--text-muted)' }}>
        {label}
      </div>
      <span className="font-serif text-3xl font-semibold tabular-nums leading-none" style={{ color: isCrit ? 'var(--negative)' : 'var(--text)' }}>
        {value}
      </span>
    </div>
  )
}
