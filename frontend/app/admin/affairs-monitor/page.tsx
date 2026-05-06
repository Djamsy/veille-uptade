'use client'

/**
 * Monitoring temps réel de la création d'affaires — Admin only.
 *
 * Permet de :
 * - Voir les affaires créées sur les dernières 24/48/72 h
 * - Voir le flux d'événements timeline (created / merged / archived / bmg_change)
 * - Voir les articles que le pipeline refuse d'absorber, avec la raison
 *   (boule-de-neige bloquée, hors-zone, communes différentes…)
 * - Lancer un reset complet (avec confirmation) pour observer le pipeline à neuf
 *
 * Auto-refresh : 30 s.
 */

import { useEffect, useMemo, useState, useCallback } from 'react'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
const AUTO_REFRESH_MS = 30_000

function authHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function adminGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

async function adminPost<T>(path: string): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, { method: 'POST', headers: authHeaders() })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

interface Overview {
  window_hours: number
  since: string
  now: string
  affairs: {
    created: number
    by_status: { status: string; count: number }[]
    by_theme: { theme: string; count: number }[]
  }
  timeline_events: { event: string; count: number }[]
  articles: {
    processed: number
    unprocessed_pending: number
    ignored_by_reason: { reason: string; count: number }[]
  }
}

interface AffairRow {
  _id: string
  title: string
  theme?: string
  status?: string
  created_at?: string
  updated_at?: string
  items_count: number
  gravity_score?: number
  bmg?: number
  communes?: string[]
  entities?: string[]
}

interface TimelineEvent {
  _id: string
  affair_id?: string
  event?: string
  details?: any
  timestamp?: string
}

interface BlockedArticle {
  _id: string
  article_id?: string
  title?: string
  source?: string
  scraped_at?: string
  _ignore_reason?: string
  _affair_attempts?: number
  theme?: string
}

function fmtTime(s?: string | null): string {
  if (!s) return '—'
  try {
    const d = new Date(s)
    return d.toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
  } catch { return s }
}

function StatusBadge({ status }: { status?: string }) {
  if (!status) return <span className="text-gray-500">—</span>
  const colors: Record<string, string> = {
    active: 'bg-emerald-900/40 text-emerald-300 border-emerald-700',
    stale: 'bg-amber-900/40 text-amber-300 border-amber-700',
    archived: 'bg-gray-800 text-gray-400 border-gray-700',
  }
  const cls = colors[status] || 'bg-gray-800 text-gray-300 border-gray-700'
  return <span className={`px-2 py-0.5 rounded border text-xs ${cls}`}>{status}</span>
}

export default function AffairsMonitorPage() {
  const [hours, setHours] = useState(24)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [affairs, setAffairs] = useState<AffairRow[]>([])
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [blocked, setBlocked] = useState<BlockedArticle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [resetting, setResetting] = useState(false)
  const [resetMsg, setResetMsg] = useState('')
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const refresh = useCallback(async () => {
    try {
      setError('')
      const [o, a, t, b] = await Promise.all([
        adminGet<Overview>(`/api/affairs/monitor/overview?hours=${hours}`),
        adminGet<{ items: AffairRow[] }>(`/api/affairs/monitor/recent-affairs?limit=50`),
        adminGet<{ items: TimelineEvent[] }>(`/api/affairs/monitor/timeline?limit=80`),
        adminGet<{ items: BlockedArticle[] }>(`/api/affairs/monitor/blocked-articles?limit=50&hours=${hours * 2}`),
      ])
      setOverview(o)
      setAffairs(a.items)
      setTimeline(t.items)
      setBlocked(b.items)
      setLastRefresh(new Date())
    } catch (e: any) {
      setError(`Chargement : ${e.message}`)
    } finally {
      setLoading(false)
    }
  }, [hours])

  useEffect(() => {
    setLoading(true)
    refresh()
  }, [refresh])

  useEffect(() => {
    const id = setInterval(refresh, AUTO_REFRESH_MS)
    return () => clearInterval(id)
  }, [refresh])

  async function handleReset() {
    if (!window.confirm(
      "⚠️ Ultime clear : supprime TOUTES les affaires, timeline, clusters, et reset les flags articles.\n\n" +
      "Le pipeline sera observé à neuf au prochain cycle d'enrichissement.\n\n" +
      "Confirmer ?"
    )) return
    setResetting(true)
    setResetMsg('')
    try {
      const r = await adminPost<any>('/api/affairs/monitor/reset?confirm=yes-reset-affairs')
      setResetMsg(
        `✅ Reset OK — ${r.affairs_deleted} affaires, ${r.timeline_deleted} événements, ` +
        `${r.candidates_deleted} candidats, ${r.clusters_deleted} clusters supprimés. ` +
        `${r.articles_reset} articles réinitialisés.`
      )
      await refresh()
    } catch (e: any) {
      setError(`Reset : ${e.message}`)
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      <div className="max-w-7xl mx-auto">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Monitoring création d'affaires</h1>
            <p className="text-sm text-gray-400 mt-1">
              Audit temps réel — créations, blocages anti boule-de-neige, articles refusés.
              Auto-refresh 30 s.
            </p>
          </div>
          <div className="flex gap-2">
            {[6, 24, 48, 72, 168].map(h => (
              <button
                key={h}
                onClick={() => setHours(h)}
                className={`px-3 py-1.5 rounded text-sm border ${
                  hours === h
                    ? 'bg-blue-600 border-blue-500 text-white'
                    : 'bg-gray-900 border-gray-700 text-gray-300'
                }`}
              >
                {h === 168 ? '7 j' : h + ' h'}
              </button>
            ))}
            <button
              onClick={refresh}
              className="px-3 py-1.5 rounded text-sm border bg-gray-900 border-gray-700 text-gray-300 hover:border-gray-500"
            >
              ↻ Refresh
            </button>
            <button
              onClick={handleReset}
              disabled={resetting}
              className="px-3 py-1.5 rounded text-sm border bg-red-900/40 border-red-700 text-red-200 hover:bg-red-800/50 disabled:opacity-50"
            >
              {resetting ? 'Reset…' : '⚠️ Ultime clear'}
            </button>
          </div>
        </header>

        {error && <div className="mb-4 p-3 rounded bg-red-900/30 border border-red-700 text-red-300 text-sm">{error}</div>}
        {resetMsg && <div className="mb-4 p-3 rounded bg-emerald-900/30 border border-emerald-700 text-emerald-300 text-sm">{resetMsg}</div>}
        {lastRefresh && <div className="mb-4 text-xs text-gray-500">Dernier refresh : {lastRefresh.toLocaleTimeString('fr-FR')}</div>}

        {/* KPIs */}
        {overview && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-xs text-gray-400">Affaires créées</div>
              <div className="text-2xl font-bold mt-1 text-emerald-400">{overview.affairs.created}</div>
              <div className="text-xs text-gray-500 mt-1">sur {hours} h</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-xs text-gray-400">Articles processés</div>
              <div className="text-2xl font-bold mt-1">{overview.articles.processed}</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-xs text-gray-400">En attente</div>
              <div className="text-2xl font-bold mt-1 text-amber-400">{overview.articles.unprocessed_pending}</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-xs text-gray-400">Articles ignorés</div>
              <div className="text-2xl font-bold mt-1 text-red-400">
                {overview.articles.ignored_by_reason.reduce((s, r) => s + r.count, 0)}
              </div>
            </div>
          </div>
        )}

        {/* Distributions */}
        {overview && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Statut des affaires créées</h3>
              {overview.affairs.by_status.length === 0 && <div className="text-sm text-gray-500">—</div>}
              <ul className="text-sm space-y-1">
                {overview.affairs.by_status.map(s => (
                  <li key={s.status} className="flex justify-between">
                    <span><StatusBadge status={s.status} /></span>
                    <span className="font-mono">{s.count}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Top thèmes</h3>
              {overview.affairs.by_theme.length === 0 && <div className="text-sm text-gray-500">—</div>}
              <ul className="text-sm space-y-1">
                {overview.affairs.by_theme.map(t => (
                  <li key={t.theme} className="flex justify-between">
                    <span className="text-gray-300 truncate pr-2">{t.theme}</span>
                    <span className="font-mono text-blue-400">{t.count}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Raisons de blocage</h3>
              {overview.articles.ignored_by_reason.length === 0 && <div className="text-sm text-gray-500">Aucun blocage</div>}
              <ul className="text-sm space-y-1">
                {overview.articles.ignored_by_reason.slice(0, 8).map(r => (
                  <li key={r.reason} className="flex justify-between">
                    <span className="text-gray-300 truncate pr-2">{r.reason}</span>
                    <span className="font-mono text-red-400">{r.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Affaires récentes */}
        <div className="mb-6 bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex justify-between items-center">
            <h3 className="font-semibold">Affaires créées les plus récentes</h3>
            <span className="text-xs text-gray-500">{affairs.length} dernières</span>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-950 text-gray-400 text-xs">
              <tr>
                <th className="text-left p-3">Créée</th>
                <th className="text-left p-3">Titre</th>
                <th className="text-left p-3">Thème</th>
                <th className="text-left p-3">Statut</th>
                <th className="text-right p-3">Articles</th>
                <th className="text-right p-3">Gravité</th>
                <th className="text-left p-3">Communes</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={7} className="p-4 text-center text-gray-500">Chargement…</td></tr>}
              {!loading && affairs.length === 0 && (
                <tr><td colSpan={7} className="p-4 text-center text-gray-500">Aucune affaire — pipeline vierge.</td></tr>
              )}
              {affairs.map(a => (
                <tr key={a._id} className="border-t border-gray-800 hover:bg-gray-850/40">
                  <td className="p-3 text-gray-400 whitespace-nowrap">{fmtTime(a.created_at)}</td>
                  <td className="p-3 max-w-xs truncate">{a.title}</td>
                  <td className="p-3 text-gray-400">{a.theme || '—'}</td>
                  <td className="p-3"><StatusBadge status={a.status} /></td>
                  <td className="p-3 text-right font-mono">{a.items_count}</td>
                  <td className="p-3 text-right font-mono">{a.gravity_score?.toFixed(2) ?? '—'}</td>
                  <td className="p-3 text-gray-400 truncate max-w-xs">{(a.communes || []).join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Timeline + Blocked side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800">
              <h3 className="font-semibold">Flux d'événements</h3>
              <p className="text-xs text-gray-500 mt-1">created · cluster_merged · archived · bmg_change</p>
            </div>
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <tbody>
                  {timeline.length === 0 && <tr><td className="p-3 text-gray-500">Aucun événement.</td></tr>}
                  {timeline.map(ev => (
                    <tr key={ev._id} className="border-t border-gray-800/60">
                      <td className="p-2 text-gray-500 whitespace-nowrap w-32">{fmtTime(ev.timestamp)}</td>
                      <td className="p-2">
                        <span className="px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-300 text-xs">{ev.event}</span>
                      </td>
                      <td className="p-2 text-gray-400 truncate max-w-xs">
                        <code className="text-xs">{JSON.stringify(ev.details).slice(0, 100)}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800">
              <h3 className="font-semibold">Articles refusés (anti boule-de-neige)</h3>
              <p className="text-xs text-gray-500 mt-1">Le pipeline n'a pas voulu les rattacher à une affaire.</p>
            </div>
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <tbody>
                  {blocked.length === 0 && <tr><td className="p-3 text-gray-500">Aucun article refusé.</td></tr>}
                  {blocked.map(b => (
                    <tr key={b._id} className="border-t border-gray-800/60">
                      <td className="p-2 text-gray-500 whitespace-nowrap w-24">{fmtTime(b.scraped_at)}</td>
                      <td className="p-2">
                        <div className="text-gray-300 truncate max-w-md">{b.title}</div>
                        <div className="text-gray-500 mt-0.5">
                          <span className="text-red-400">{b._ignore_reason}</span>
                          {b._affair_attempts ? <span className="ml-2">tentatives : {b._affair_attempts}</span> : null}
                          {b.source ? <span className="ml-2">· {b.source}</span> : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <footer className="mt-6 text-xs text-gray-500">
          Audit pipeline · Décide si le modèle « lifecycle continu » tient ou s'il faut basculer en « affaires journalières ».
        </footer>
      </div>
    </div>
  )
}
