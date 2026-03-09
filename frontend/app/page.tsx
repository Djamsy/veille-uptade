'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../components/Sidebar'
import BmgGauge from '../components/BmgGauge'
import {
  fetchEnrichedDashboard,
  runFullCycle,
  runReaffiliate,
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
    politique: 'rgba(168,85,247,0.15)_#c084fc_rgba(168,85,247,0.3)',
    economie: 'rgba(16,185,129,0.15)_#34d399_rgba(16,185,129,0.3)',
    economie_emploi: 'rgba(16,185,129,0.15)_#34d399_rgba(16,185,129,0.3)',
    social: 'rgba(96,165,250,0.15)_#93c5fd_rgba(96,165,250,0.3)',
    sante_social: 'rgba(251,113,133,0.15)_#fda4af_rgba(251,113,133,0.3)',
    environnement: 'rgba(74,222,128,0.15)_#86efac_rgba(74,222,128,0.3)',
    eau_env: 'rgba(74,222,128,0.15)_#86efac_rgba(74,222,128,0.3)',
    energie_transports: 'rgba(251,146,60,0.15)_#fdba74_rgba(251,146,60,0.3)',
    sante: 'rgba(251,113,133,0.15)_#fda4af_rgba(251,113,133,0.3)',
    justice: 'rgba(251,191,36,0.15)_#fde68a_rgba(251,191,36,0.3)',
    securite: 'rgba(248,113,113,0.15)_#fca5a5_rgba(248,113,113,0.3)',
    securite_justice: 'rgba(248,113,113,0.15)_#fca5a5_rgba(248,113,113,0.3)',
    education: 'rgba(129,140,248,0.15)_#a5b4fc_rgba(129,140,248,0.3)',
    culture: 'rgba(244,114,182,0.15)_#f9a8d4_rgba(244,114,182,0.3)',
    culture_patrimoine: 'rgba(244,114,182,0.15)_#f9a8d4_rgba(244,114,182,0.3)',
    sport: 'rgba(34,211,238,0.15)_#67e8f9_rgba(34,211,238,0.3)',
    infrastructure: 'rgba(251,146,60,0.15)_#fdba74_rgba(251,146,60,0.3)',
  }
  const parts = (map[theme] || 'rgba(148,163,184,0.15)_#cbd5e1_rgba(148,163,184,0.3)').split('_')
  return parts.join('_')
}

function ThemeBadge({ theme }: { theme: string }) {
  const parts = themeColor(theme).split('_')
  return (
    <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{
      background: parts[0], color: parts[1], border: `1px solid ${parts[2]}`,
    }}>
      {themeLabel(theme)}
    </span>
  )
}

// ── Rate Bar ────────────────────────────────────────────
function RateBar({ label, rate, count, total, color }: {
  label: string; rate: number; count: number; total: number; color: string
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'rgba(255,255,255,0.5)' }}>{label}</span>
        <span className="text-xs font-bold" style={{ color }}>{rate}%</span>
      </div>
      <div className="progress-bar-bg h-1.5">
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.min(100, rate)}%`, background: color, boxShadow: `0 0 8px ${color}40` }} />
      </div>
      <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>{count} / {total}</p>
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
            <div className="rounded-t-sm transition-all duration-500"
              style={{
                height: `${(d.articles / maxArticles) * 100}%`,
                minHeight: d.articles > 0 ? '3px' : '0',
                background: 'linear-gradient(180deg, #818cf8, #6366f1)',
                boxShadow: d.articles > 0 ? '0 0 6px rgba(99,102,241,0.4)' : 'none',
              }} />
            <div className="rounded-t-sm transition-all duration-500"
              style={{
                height: `${(d.events / maxEvents) * 40}%`,
                minHeight: d.events > 0 ? '2px' : '0',
                background: 'rgba(168,85,247,0.6)',
              }} />
          </div>
          <span className="text-[9px] leading-none" style={{ color: 'rgba(255,255,255,0.25)' }}>
            {d.label.split(' ')[0]}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Skeleton ──────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="glass-card-static p-5">
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
      <div className="glass-card p-4 cursor-pointer card-hover h-full">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white truncate">
              {affair.title || affair.primary_entity || 'Affaire'}
            </h3>
            <p className="text-xs mt-0.5" style={{ color: 'rgba(255,255,255,0.35)' }}>
              {affair.primary_entity && affair.title !== affair.primary_entity
                ? affair.primary_entity
                : timeAgo(affair.last_activity || affair.created_at)}
            </p>
          </div>
          <BmgGauge value={(affair.bmg || 0) * 100} size={52} />
        </div>
        <div className="flex flex-wrap gap-1 mb-2">
          <ThemeBadge theme={affair.theme} />
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)' }}>
            {affair.item_count || 0} items
          </span>
          {(affair.source_types?.length || 0) >= 2 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
              style={{ background: 'rgba(99,102,241,0.1)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.2)' }}>
              multi-canal
            </span>
          )}
        </div>
        <div className="flex items-center justify-between text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
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
      <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl cursor-pointer transition-all"
        style={{
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.2)',
        }}
      >
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse flex-shrink-0"
          style={{ boxShadow: '0 0 8px rgba(239,68,68,0.5)' }} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">
            {affair.title || affair.primary_entity}
          </p>
        </div>
        <span className="text-xs font-medium flex-shrink-0" style={{ color: '#f87171' }}>
          BMG {Math.round((affair.bmg || 0) * 100)}
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
        <p className="text-xs truncate" style={{ color: 'rgba(255,255,255,0.5)' }}>
          {(event.details as Record<string, string>)?.title ||
           (event.details as Record<string, string>)?.reason ||
           event.event}
        </p>
        <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{timeAgo(event.timestamp)}</p>
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
  const [reaffiliating, setReaffiliating] = useState(false)
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

  const handleReaffiliate = async () => {
    setReaffiliating(true)
    try { await runReaffiliate(); await loadData() }
    catch (e: unknown) { console.error('Reaffiliate error:', e) }
    finally { setReaffiliating(false) }
  }

  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-64 flex-1 p-8 min-h-screen">
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
      <main className="ml-64 flex-1 p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Tableau de bord</h1>
              <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
                MAJ : {lastRefresh.toLocaleTimeString('fr-FR')} — 7 derniers jours
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={loadData} className="btn-glass px-3 py-1.5 text-xs">
                ↻ Rafraîchir
              </button>
              <button onClick={handleRunCycle} disabled={cycleRunning} className="btn-primary px-4 py-1.5 text-xs">
                {cycleRunning ? '⟳ Cycle en cours...' : '▶ Lancer le cycle'}
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-4 px-4 py-3 rounded-xl text-sm" style={{
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', color: '#f87171'
            }}>{error}</div>
          )}

          {/* Alertes critiques */}
          {criticals.length > 0 && (
            <div className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"
                  style={{ boxShadow: '0 0 8px rgba(239,68,68,0.5)' }} />
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#f87171' }}>
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
            {[
              { label: 'Affaires actives', value: stats?.affairs_active ?? 0, sub: `${stats?.affairs_stale ?? 0} en veille`, color: '#818cf8' },
              { label: 'Articles 7j', value: coverage?.total_articles_7d ?? 0, sub: `${coverage?.enriched_articles_7d ?? 0} enrichis`, color: '#f0f0f5' },
              { label: 'Taux affiliation', value: `${coverage?.affiliation_rate ?? 0}%`, sub: `${coverage?.affiliated_articles_7d ?? 0} affiliés`,
                color: (coverage?.affiliation_rate ?? 0) >= 60 ? '#34d399' : (coverage?.affiliation_rate ?? 0) >= 30 ? '#fbbf24' : '#f87171' },
              { label: 'Radio 7j', value: coverage?.total_transcriptions_7d ?? 0, sub: `${coverage?.radio_rate ?? 0}% traités`, color: '#c084fc' },
            ].map((metric, i) => (
              <div key={i} className="glass-card-static p-4">
                <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>{metric.label}</p>
                <p className="text-3xl font-bold" style={{ color: metric.color }}>{metric.value}</p>
                <p className="text-[10px] mt-0.5" style={{ color: 'rgba(255,255,255,0.2)' }}>{metric.sub}</p>
              </div>
            ))}
          </div>

          {/* ── ROW 2 : Couverture + Activité ─────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {/* Taux de couverture */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Couverture pipeline
              </h2>
              <div className="space-y-4">
                <RateBar label="Enrichissement IA" rate={coverage?.enrichment_rate ?? 0}
                  count={coverage?.enriched_articles_7d ?? 0} total={coverage?.total_articles_7d ?? 0}
                  color="#818cf8" />
                <RateBar label="Affiliation aux affaires" rate={coverage?.affiliation_rate ?? 0}
                  count={coverage?.affiliated_articles_7d ?? 0} total={coverage?.total_articles_7d ?? 0}
                  color="#34d399" />
                <RateBar label="Radio traitées" rate={coverage?.radio_rate ?? 0}
                  count={coverage?.processed_transcriptions_7d ?? 0} total={coverage?.total_transcriptions_7d ?? 0}
                  color="#c084fc" />
              </div>
            </div>

            {/* Activité 7 jours */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Activité 7 jours
              </h2>
              {activity.length > 0 ? (
                <>
                  <ActivityChart data={activity} />
                  <div className="flex items-center gap-4 mt-3 justify-center">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full" style={{ background: '#6366f1' }} />
                      <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.3)' }}>Articles</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full" style={{ background: 'rgba(168,85,247,0.6)' }} />
                      <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.3)' }}>Événements</span>
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-xs text-center py-8" style={{ color: 'rgba(255,255,255,0.25)' }}>Pas de données</p>
              )}
            </div>

            {/* Répartition thématique + sources */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Thèmes des affaires
              </h2>
              {Object.keys(themes).length > 0 ? (
                <div className="space-y-2 mb-4">
                  {Object.entries(themes).map(([theme, count]) => {
                    const maxCount = Math.max(...Object.values(themes))
                    return (
                      <div key={theme} className="flex items-center gap-2">
                        <span className="flex-shrink-0"><ThemeBadge theme={theme} /></span>
                        <div className="flex-1 progress-bar-bg h-1.5">
                          <div className="h-full rounded-full" style={{
                            width: `${(count / maxCount) * 100}%`,
                            background: 'linear-gradient(90deg, #6366f1, #818cf8)',
                          }} />
                        </div>
                        <span className="text-[10px] w-4 text-right" style={{ color: 'rgba(255,255,255,0.3)' }}>{count}</span>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs mb-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Aucune affaire active</p>
              )}

              {sources.length > 0 && (
                <>
                  <h3 className="text-[10px] uppercase tracking-wider mb-2 pt-3" style={{
                    color: 'rgba(255,255,255,0.25)', borderTop: '1px solid rgba(255,255,255,0.06)'
                  }}>
                    Sources actives 7j
                  </h3>
                  <div className="flex flex-wrap gap-1">
                    {sources.map((s, i) => (
                      <span key={i} className="text-[10px] px-2 py-0.5 rounded-full" style={{
                        background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)'
                      }}>
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
                <h2 className="text-sm font-semibold text-white">Affaires majeures</h2>
                <Link href="/affairs" className="text-xs transition-colors" style={{ color: '#818cf8' }}>
                  Voir tout →
                </Link>
              </div>
              {topAffairs.length === 0 ? (
                <div className="glass-card-static p-10 text-center">
                  <p className="text-sm" style={{ color: 'rgba(255,255,255,0.35)' }}>Aucune affaire active</p>
                  <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.2)' }}>Lancez le cycle pour détecter de nouvelles affaires</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                  {topAffairs.slice(0, 9).map((affair) => <AffairCard key={affair._id} affair={affair} />)}
                </div>
              )}
            </div>

            {/* Sidebar : Timeline + Entités */}
            <div className="space-y-4">
              <div className="glass-card-static p-4">
                <h3 className="text-[10px] uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.3)' }}>
                  Activité récente
                </h3>
                {timeline.length > 0 ? (
                  <div className="space-y-0" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
                    {timeline.slice(0, 8).map((evt) => (
                      <TimelineItem key={evt._id} event={evt} />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs py-4 text-center" style={{ color: 'rgba(255,255,255,0.25)' }}>Aucune activité</p>
                )}
              </div>

              {entities.length > 0 && (
                <div className="glass-card-static p-4">
                  <h3 className="text-[10px] uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.3)' }}>
                    Top entités
                  </h3>
                  <div className="space-y-1">
                    {entities.slice(0, 10).map((e, i) => (
                      <div key={i} className="flex items-center justify-between">
                        <span className="text-xs truncate" style={{ color: 'rgba(255,255,255,0.5)' }}>{e.name}</span>
                        <span className="text-[10px] ml-2 flex-shrink-0" style={{ color: 'rgba(255,255,255,0.25)' }}>×{e.count}</span>
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
                  <h2 className="text-sm font-semibold text-white">Articles non affiliés</h2>
                  <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>Articles enrichis sans affaire — à surveiller</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-1 rounded-full" style={{
                    background: 'rgba(245,158,11,0.1)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.2)'
                  }}>
                    {orphans.length} orphelins
                  </span>
                  <button onClick={handleReaffiliate} disabled={reaffiliating}
                    className="btn-glass text-xs px-3 py-1 disabled:opacity-50">
                    {reaffiliating ? '⟳ En cours...' : '🔗 Ré-affilier'}
                  </button>
                </div>
              </div>
              <div className="glass-card-static overflow-hidden">
                <div>
                  {orphans.map((art, idx) => (
                    <div key={art._id} className="flex items-center gap-3 px-4 py-2.5"
                      style={{ borderBottom: idx < orphans.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                      <ThemeBadge theme={art.theme} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs truncate" style={{ color: 'rgba(255,255,255,0.6)' }}>{art.title}</p>
                        <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                          {art.source} — {timeAgo(art.scraped_at)}
                        </p>
                      </div>
                      <div className="flex-shrink-0 text-right">
                        <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>gravité</p>
                        <p className={`text-xs font-bold`} style={{
                          color: art.gravity_score >= 0.7 ? '#f87171' : art.gravity_score >= 0.4 ? '#fbbf24' : 'rgba(255,255,255,0.3)'
                        }}>{Math.round(art.gravity_score * 100)}%</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── ROW 5 : Pipeline technique ─────────────── */}
          {stats && (
            <div className="glass-card-static p-4">
              <h2 className="text-[10px] uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.3)' }}>
                Pipeline technique
              </h2>
              <div className="flex items-center gap-4 overflow-x-auto">
                {[
                  { label: 'Candidats', value: stats.candidates_total, sub: 'Ingestion', color: '#fbbf24', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.2)' },
                  { label: 'Non classés', value: stats.candidates_unclustered, sub: 'En attente', color: '#f87171', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.2)' },
                  { label: 'Clusters', value: stats.clusters_active, sub: 'Groupement', color: '#c084fc', bg: 'rgba(168,85,247,0.1)', border: 'rgba(168,85,247,0.2)' },
                  { label: 'Affaires', value: stats.affairs_active, sub: 'Promues', color: '#818cf8', bg: 'rgba(99,102,241,0.1)', border: 'rgba(99,102,241,0.2)' },
                  { label: 'En veille', value: stats.affairs_stale, sub: 'Archivage', color: 'rgba(255,255,255,0.4)', bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.08)' },
                ].map((step, i, arr) => (
                  <div key={i} className="flex items-center gap-3 flex-shrink-0">
                    <div className="w-9 h-9 rounded-full flex items-center justify-center"
                      style={{ background: step.bg, border: `1px solid ${step.border}` }}>
                      <span className="text-xs font-bold" style={{ color: step.color }}>{step.value ?? 0}</span>
                    </div>
                    <div>
                      <p className="text-[10px] font-medium" style={{ color: 'rgba(255,255,255,0.5)' }}>{step.label}</p>
                      <p className="text-[9px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{step.sub}</p>
                    </div>
                    {i < arr.length - 1 && (
                      <svg className="w-4 h-4" style={{ color: 'rgba(255,255,255,0.15)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
