'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../components/Sidebar'
import BmgGauge from '../components/BmgGauge'
import {
  fetchEnrichedDashboard,
  runFullCycle,
  type EnrichedDashboardData,
  type Affair,
  type DailyActivity,
  type TopEntity,
  type TopSource,
  type OrphanArticle,
  type TimelineEvent,
} from '../lib/api'

// ── Helpers ──────────────────────────────────────────────
function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return 'à l\'instant'
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

function themeLabel(theme: string): string {
  const map: Record<string, string> = {
    politique: 'Politique', economie: 'Économie', social: 'Social',
    economie_emploi: 'Économie', eau_env: 'Environnement',
    energie_transports: 'Transports', sante_social: 'Santé',
    securite_justice: 'Justice', education: 'Éducation',
    culture_patrimoine: 'Culture', sport: 'Sport', general: 'Général',
    environnement: 'Environnement', sante: 'Santé', justice: 'Justice',
    culture: 'Culture', securite: 'Sécurité', infrastructure: 'Infra',
  }
  return map[theme] || theme
}

function themeColor(theme: string): string {
  const map: Record<string, string> = {
    politique: 'bg-purple-100 text-purple-700 border-purple-200',
    economie: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    economie_emploi: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    social: 'bg-blue-100 text-blue-700 border-blue-200',
    sante_social: 'bg-rose-100 text-rose-700 border-rose-200',
    environnement: 'bg-green-100 text-green-700 border-green-200',
    eau_env: 'bg-green-100 text-green-700 border-green-200',
    energie_transports: 'bg-orange-100 text-orange-700 border-orange-200',
    sante: 'bg-rose-100 text-rose-700 border-rose-200',
    justice: 'bg-amber-100 text-amber-700 border-amber-200',
    securite: 'bg-red-100 text-red-700 border-red-200',
    securite_justice: 'bg-red-100 text-red-700 border-red-200',
    education: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    culture: 'bg-pink-100 text-pink-700 border-pink-200',
    culture_patrimoine: 'bg-pink-100 text-pink-700 border-pink-200',
    sport: 'bg-cyan-100 text-cyan-700 border-cyan-200',
    infrastructure: 'bg-orange-100 text-orange-700 border-orange-200',
  }
  return map[theme] || 'bg-slate-100 text-slate-600 border-slate-200'
}

// ── Rate Bar ────────────────────────────────────────────
function RateBar({ label, rate, count, total, color }: {
  label: string; rate: number; count: number; total: number; color: string
}) {
  const barColor = rate >= 70 ? 'bg-emerald-500' : rate >= 40 ? 'bg-amber-500' : 'bg-red-400'
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-600 font-medium">{label}</span>
        <span className={`text-xs font-bold ${color}`}>{rate}%</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${Math.min(100, rate)}%` }} />
      </div>
      <p className="text-[10px] text-slate-400">{count} / {total}</p>
    </div>
  )
}

// ── Mini Activity Chart ─────────────────────────────────
function ActivityChart({ data }: { data: DailyActivity[] }) {
  const maxArticles = Math.max(...data.map(d => d.articles), 1)
  const maxEvents = Math.max(...data.map(d => d.events), 1)
  return (
    <div className="flex items-end gap-1.5 h-24">
      {data.map((d, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
          <div className="w-full flex flex-col-reverse gap-0.5" style={{ height: '72px' }}>
            <div className="bg-teal-400 rounded-t-sm transition-all duration-300"
              style={{ height: `${(d.articles / maxArticles) * 100}%`, minHeight: d.articles > 0 ? '3px' : '0' }} />
            <div className="bg-purple-400 rounded-t-sm transition-all duration-300"
              style={{ height: `${(d.events / maxEvents) * 40}%`, minHeight: d.events > 0 ? '2px' : '0' }} />
          </div>
          <span className="text-[9px] text-slate-400 leading-none">{d.label.split(' ')[0]}</span>
        </div>
      ))}
    </div>
  )
}

// ── Skeleton ──────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="skeleton h-4 w-24 mb-3" />
      <div className="skeleton h-8 w-16 mb-2" />
      <div className="skeleton h-3 w-20" />
    </div>
  )
}

// ── Affair Card ──────────────────────────────────────────
function AffairCard({ affair }: { affair: Affair }) {
  return (
    <Link href={`/affairs/${affair._id}`}>
      <div className="bg-white rounded-xl border border-slate-200 p-4 card-hover cursor-pointer shadow-sm">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-slate-800 truncate">
              {affair.title || affair.primary_entity || 'Affaire'}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {affair.primary_entity && affair.title !== affair.primary_entity
                ? affair.primary_entity
                : timeAgo(affair.last_activity || affair.created_at)}
            </p>
          </div>
          <BmgGauge value={affair.bmg || 0} size={52} />
        </div>
        <div className="flex flex-wrap gap-1 mb-2">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${themeColor(affair.theme)}`}>
            {themeLabel(affair.theme)}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-50 text-slate-500 border border-slate-200">
            {affair.item_count || 0} items
          </span>
          {(affair.source_types?.length || 0) >= 2 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-50 text-teal-600 border border-teal-200">
              multi-canal
            </span>
          )}
        </div>
        <div className="flex items-center justify-between text-[10px] text-slate-400">
          <span>Gravité {Math.round((affair.gravity_score || 0) * 100)}%</span>
          <span>{timeAgo(affair.last_activity || affair.created_at)}</span>
        </div>
      </div>
    </Link>
  )
}

// ── Alert Row ────────────────────────────────────────────
function AlertRow({ affair }: { affair: Affair }) {
  return (
    <Link href={`/affairs/${affair._id}`}>
      <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-red-50 border border-red-200 hover:bg-red-100 transition-colors cursor-pointer">
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-800 truncate">
            {affair.title || affair.primary_entity}
          </p>
        </div>
        <span className="text-xs text-red-600 font-medium flex-shrink-0">
          BMG {Math.round(affair.bmg || 0)}
        </span>
      </div>
    </Link>
  )
}

// ── Timeline Event ───────────────────────────────────────
function TimelineItem({ event }: { event: TimelineEvent }) {
  const iconMap: Record<string, string> = {
    created: '🆕', article_added: '📰', radio_topic_added: '📻',
    gravity_update: '📊', archived: '📦', expired: '⏰',
  }
  return (
    <div className="flex items-start gap-2 py-1.5">
      <span className="text-xs flex-shrink-0">{iconMap[event.event] || '•'}</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-600 truncate">
          {(event.details as Record<string, string>)?.title ||
           (event.details as Record<string, string>)?.reason ||
           event.event}
        </p>
        <p className="text-[10px] text-slate-400">{timeAgo(event.timestamp)}</p>
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ════════════════════════════════════════════════════════════
export default function DashboardPage() {
  const [data, setData] = useState<EnrichedDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cycleRunning, setCycleRunning] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const loadData = useCallback(async () => {
    try {
      const result = await fetchEnrichedDashboard()
      setData(result)
      setError('')
      setLastRefresh(new Date())
    } catch (e: unknown) {
      setError((e as Error).message || 'Erreur de connexion')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 90_000)
    return () => clearInterval(interval)
  }, [loadData])

  const handleRunCycle = async () => {
    setCycleRunning(true)
    try { await runFullCycle(); await loadData() }
    catch (e: unknown) { console.error('Cycle error:', e) }
    finally { setCycleRunning(false) }
  }

  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-64 flex-1 p-8 min-h-screen bg-[#faf9f6]">
          <div className="max-w-7xl mx-auto">
            <div className="skeleton h-8 w-48 mb-8" />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
            </div>
          </div>
        </main>
      </div>
    )
  }

  const topAffairs = data?.top_affairs || []
  const criticals = data?.critical_alerts || []
  const stats = data?.stats
  const coverage = data?.coverage
  const themes = data?.themes_distribution || {}
  const entities = data?.top_entities || []
  const activity = data?.daily_activity || []
  const orphans = data?.orphan_articles || []
  const timeline = data?.recent_timeline || []
  const sources = data?.top_sources || []

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 p-6 min-h-screen bg-[#faf9f6]">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-slate-800">Tableau de bord</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                MAJ : {lastRefresh.toLocaleTimeString('fr-FR')} — 7 derniers jours
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={loadData}
                className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-500 text-xs hover:bg-slate-50 transition-colors shadow-sm">
                ↻ Rafraîchir
              </button>
              <button onClick={handleRunCycle} disabled={cycleRunning}
                className="px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-white text-xs font-medium transition-colors disabled:opacity-50 shadow-sm">
                {cycleRunning ? '⟳ Cycle en cours...' : '▶ Lancer le cycle'}
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-600 text-sm">{error}</div>
          )}

          {/* Alertes critiques */}
          {criticals.length > 0 && (
            <div className="mb-6">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <h2 className="text-xs font-semibold text-red-600 uppercase tracking-wider">
                  Alertes ({criticals.length})
                </h2>
              </div>
              <div className="space-y-1.5">
                {criticals.slice(0, 3).map((a) => <AlertRow key={a._id} affair={a} />)}
              </div>
            </div>
          )}

          {/* ── ROW 1 : Métriques clés ─────────────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
              <p className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Affaires actives</p>
              <p className="text-3xl font-bold text-teal-600">{stats?.affairs_active ?? 0}</p>
              <p className="text-[10px] text-slate-400 mt-0.5">{stats?.affairs_stale ?? 0} en veille</p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
              <p className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Articles 7j</p>
              <p className="text-3xl font-bold text-slate-800">{coverage?.total_articles_7d ?? 0}</p>
              <p className="text-[10px] text-slate-400 mt-0.5">{coverage?.enriched_articles_7d ?? 0} enrichis</p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
              <p className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Taux affiliation</p>
              <p className={`text-3xl font-bold ${
                (coverage?.affiliation_rate ?? 0) >= 60 ? 'text-emerald-600' :
                (coverage?.affiliation_rate ?? 0) >= 30 ? 'text-amber-600' : 'text-red-500'
              }`}>{coverage?.affiliation_rate ?? 0}%</p>
              <p className="text-[10px] text-slate-400 mt-0.5">{coverage?.affiliated_articles_7d ?? 0} affiliés</p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
              <p className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Radio 7j</p>
              <p className="text-3xl font-bold text-purple-600">{coverage?.total_transcriptions_7d ?? 0}</p>
              <p className="text-[10px] text-slate-400 mt-0.5">{coverage?.radio_rate ?? 0}% traités</p>
            </div>
          </div>

          {/* ── ROW 2 : Couverture + Activité ─────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {/* Taux de couverture */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Couverture pipeline</h2>
              <div className="space-y-4">
                <RateBar label="Enrichissement IA" rate={coverage?.enrichment_rate ?? 0}
                  count={coverage?.enriched_articles_7d ?? 0} total={coverage?.total_articles_7d ?? 0}
                  color="text-blue-600" />
                <RateBar label="Affiliation aux affaires" rate={coverage?.affiliation_rate ?? 0}
                  count={coverage?.affiliated_articles_7d ?? 0} total={coverage?.total_articles_7d ?? 0}
                  color="text-teal-600" />
                <RateBar label="Radio traitées" rate={coverage?.radio_rate ?? 0}
                  count={coverage?.processed_transcriptions_7d ?? 0} total={coverage?.total_transcriptions_7d ?? 0}
                  color="text-purple-600" />
              </div>
            </div>

            {/* Activité 7 jours */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Activité 7 jours</h2>
              {activity.length > 0 ? (
                <>
                  <ActivityChart data={activity} />
                  <div className="flex items-center gap-4 mt-3 justify-center">
                    <div className="flex items-center gap-1">
                      <div className="w-2 h-2 rounded-full bg-teal-400" />
                      <span className="text-[10px] text-slate-400">Articles</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-2 h-2 rounded-full bg-purple-400" />
                      <span className="text-[10px] text-slate-400">Événements</span>
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-xs text-slate-400 text-center py-8">Pas de données</p>
              )}
            </div>

            {/* Répartition thématique + sources */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Thèmes des affaires</h2>
              {Object.keys(themes).length > 0 ? (
                <div className="space-y-2 mb-4">
                  {Object.entries(themes).map(([theme, count]) => {
                    const maxCount = Math.max(...Object.values(themes))
                    return (
                      <div key={theme} className="flex items-center gap-2">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${themeColor(theme)} flex-shrink-0`}>
                          {themeLabel(theme)}
                        </span>
                        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-teal-400 rounded-full"
                            style={{ width: `${(count / maxCount) * 100}%` }} />
                        </div>
                        <span className="text-[10px] text-slate-400 w-4 text-right">{count}</span>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs text-slate-400 mb-4">Aucune affaire active</p>
              )}

              {sources.length > 0 && (
                <>
                  <h3 className="text-[10px] text-slate-400 uppercase tracking-wider mb-2 pt-3 border-t border-slate-100">
                    Sources actives 7j
                  </h3>
                  <div className="flex flex-wrap gap-1">
                    {sources.map((s, i) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-50 text-slate-500 border border-slate-200">
                        {s.name} ({s.count})
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* ── ROW 3 : Affaires + Sidebar ─────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-6">
            {/* Affaires majeures (3 cols) */}
            <div className="lg:col-span-3">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-slate-700">Affaires majeures</h2>
                <Link href="/affairs" className="text-xs text-teal-600 hover:text-teal-500 transition-colors">
                  Voir tout →
                </Link>
              </div>
              {topAffairs.length === 0 ? (
                <div className="bg-white/60 rounded-xl border border-slate-200 p-10 text-center shadow-sm">
                  <p className="text-slate-400 text-sm">Aucune affaire active</p>
                  <p className="text-slate-300 text-xs mt-1">Lancez le cycle pour détecter de nouvelles affaires</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                  {topAffairs.slice(0, 9).map((affair) => <AffairCard key={affair._id} affair={affair} />)}
                </div>
              )}
            </div>

            {/* Sidebar : Timeline + Entités */}
            <div className="space-y-4">
              {/* Timeline récente */}
              <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                <h3 className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Activité récente</h3>
                {timeline.length > 0 ? (
                  <div className="divide-y divide-slate-50">
                    {timeline.slice(0, 8).map((evt) => (
                      <TimelineItem key={evt._id} event={evt} />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 py-4 text-center">Aucune activité</p>
                )}
              </div>

              {/* Top entités */}
              {entities.length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                  <h3 className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Top entités</h3>
                  <div className="space-y-1">
                    {entities.slice(0, 10).map((e, i) => (
                      <div key={i} className="flex items-center justify-between">
                        <span className="text-xs text-slate-600 truncate">{e.name}</span>
                        <span className="text-[10px] text-slate-400 ml-2 flex-shrink-0">×{e.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── ROW 4 : Articles orphelins ─────────────── */}
          {orphans.length > 0 && (
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h2 className="text-sm font-semibold text-slate-700">Articles non affiliés</h2>
                  <p className="text-[10px] text-slate-400">Articles enrichis sans affaire — à surveiller</p>
                </div>
                <span className="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-600 border border-amber-200">
                  {orphans.length} orphelins
                </span>
              </div>
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="divide-y divide-slate-100">
                  {orphans.map((art) => (
                    <div key={art._id} className="flex items-center gap-3 px-4 py-2.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0 ${themeColor(art.theme)}`}>
                        {themeLabel(art.theme)}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-slate-700 truncate">{art.title}</p>
                        <p className="text-[10px] text-slate-400">{art.source} — {timeAgo(art.scraped_at)}</p>
                      </div>
                      <div className="flex-shrink-0 text-right">
                        <p className="text-[10px] text-slate-400">gravité</p>
                        <p className={`text-xs font-bold ${
                          art.gravity_score >= 0.7 ? 'text-red-500' :
                          art.gravity_score >= 0.4 ? 'text-amber-500' : 'text-slate-400'
                        }`}>{Math.round(art.gravity_score * 100)}%</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── ROW 5 : Pipeline technique ─────────────── */}
          {stats && (
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
              <h2 className="text-[10px] text-slate-400 uppercase tracking-wider mb-3">Pipeline technique</h2>
              <div className="flex items-center gap-4 overflow-x-auto">
                {[
                  { label: 'Candidats', value: stats.candidates_total, sub: 'Ingestion', color: 'amber' },
                  { label: 'Non classés', value: stats.candidates_unclustered, sub: 'En attente', color: 'red' },
                  { label: 'Clusters', value: stats.clusters_active, sub: 'Groupement', color: 'purple' },
                  { label: 'Affaires', value: stats.affairs_active, sub: 'Promues', color: 'teal' },
                  { label: 'En veille', value: stats.affairs_stale, sub: 'Archivage', color: 'slate' },
                ].map((step, i, arr) => (
                  <div key={i} className="flex items-center gap-3 flex-shrink-0">
                    <div className={`w-9 h-9 rounded-full bg-${step.color}-50 border border-${step.color}-200 flex items-center justify-center`}>
                      <span className={`text-xs font-bold text-${step.color}-600`}>{step.value ?? 0}</span>
                    </div>
                    <div>
                      <p className="text-[10px] font-medium text-slate-600">{step.label}</p>
                      <p className="text-[9px] text-slate-400">{step.sub}</p>
                    </div>
                    {i < arr.length - 1 && (
                      <svg className="w-4 h-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
