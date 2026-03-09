'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import BmgGauge from '../../components/BmgGauge'
import {
  fetchAffairSystemHealth,
  fetchReconciliationHealth,
  fetchArticleIndex,
  fetchEnrichedDashboard,
  runReconciliation,
  runFullCycle,
  type SystemStats,
  type EnrichedDashboardData,
} from '../../lib/api'

// ── Helpers ──────────────────────────────────────────
function StatusDot({ ok }: { ok: boolean }) {
  return (
    <div className={`w-2.5 h-2.5 rounded-full ${ok ? 'bg-emerald-500' : 'bg-red-500'}`}
      style={ok ? { boxShadow: '0 0 8px rgba(16,185,129,0.5)' } : { boxShadow: '0 0 8px rgba(239,68,68,0.5)' }} />
  )
}

function MetricRow({ label, value, color, sub }: { label: string; value: string | number; color?: string; sub?: string }) {
  return (
    <div className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span className="text-xs" style={{ color: 'rgba(255,255,255,0.45)' }}>{label}</span>
      <div className="text-right">
        <span className="text-xs font-semibold" style={{ color: color || 'white' }}>{value}</span>
        {sub && <p className="text-[9px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{sub}</p>}
      </div>
    </div>
  )
}

function ProgressRing({ pct, color, size = 56, label }: { pct: number; color: string; size?: number; label: string }) {
  const r = (size - 8) / 2
  const c = 2 * Math.PI * r
  const dasharray = `${(pct / 100) * c} ${c}`
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="5" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="5"
          strokeDasharray={dasharray} strokeLinecap="round" />
        <text x={size / 2} y={size / 2 + 4} textAnchor="middle" fill="white" fontSize="12" fontWeight="bold"
          style={{ transform: 'rotate(90deg)', transformOrigin: '50% 50%' }}>
          {Math.round(pct)}%
        </text>
      </svg>
      <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.35)' }}>{label}</span>
    </div>
  )
}

// ════════════════════════════════════════════════════════════
// ANALYTICS PAGE
// ════════════════════════════════════════════════════════════
export default function AnalyticsPage() {
  const [health, setHealth] = useState<SystemStats | null>(null)
  const [reconHealth, setReconHealth] = useState<Record<string, any> | null>(null)
  const [indexStatus, setIndexStatus] = useState<Record<string, any> | null>(null)
  const [dashboard, setDashboard] = useState<EnrichedDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState('')

  const loadData = useCallback(async () => {
    try {
      const [h, r, idx, dash] = await Promise.allSettled([
        fetchAffairSystemHealth(),
        fetchReconciliationHealth(),
        fetchArticleIndex(),
        fetchEnrichedDashboard(),
      ])
      if (h.status === 'fulfilled') setHealth(h.value)
      if (r.status === 'fulfilled') setReconHealth(r.value)
      if (idx.status === 'fulfilled') setIndexStatus(idx.value)
      if (dash.status === 'fulfilled') setDashboard(dash.value)
    } catch (e) {
      console.error(e)
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleAction = async (action: string, fn: () => Promise<any>) => {
    setActionLoading(action)
    try { await fn(); await loadData() }
    catch (e) { console.error(`Action ${action} failed:`, e) }
    finally { setActionLoading('') }
  }

  // ── Loading ─────────────────
  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-64 flex-1 p-8 min-h-screen">
          <div className="max-w-[1400px] mx-auto">
            <div className="skeleton h-8 w-40 mb-8" />
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="glass-card-static p-5"><div className="skeleton h-4 w-20 mb-3" /><div className="skeleton h-12 w-full" /></div>
              ))}
            </div>
          </div>
        </main>
      </div>
    )
  }

  const coverage = dashboard?.coverage
  const trends = dashboard?.trends
  const gravDist = dashboard?.gravity_distribution
  const sentDist = dashboard?.sentiment_distribution || {}
  const priorityCounts = dashboard?.priority_counts || {}
  const avgBmg = dashboard?.avg_bmg || 0
  const avgGravity = dashboard?.avg_gravity || 0
  const topSources = dashboard?.top_sources || []
  const topEntities = dashboard?.top_entities || []

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 p-8 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Analytics</h1>
              <p className="text-sm mt-0.5" style={{ color: 'rgba(255,255,255,0.35)' }}>
                Performance du pipeline, qualité des données et métriques système
              </p>
            </div>
            <button onClick={loadData} className="btn-glass px-3 py-2 text-sm">↻ Rafraîchir</button>
          </div>

          {/* ── ROW 1 : Système Health Cards ───────── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            {/* Pipeline status */}
            <div className="glass-card-static p-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.3)' }}>Pipeline</p>
                <StatusDot ok={health?.status === 'healthy'} />
              </div>
              <p className="text-2xl font-bold" style={{ color: health?.status === 'healthy' ? '#34d399' : '#f87171' }}>
                {health?.status === 'healthy' ? 'OK' : 'Erreur'}
              </p>
              <p className="text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.2)' }}>
                {health?.affairs_active ?? 0} affaires · {health?.clusters_active ?? 0} clusters
              </p>
            </div>

            {/* Enrichissement */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.3)' }}>Enrichissement IA</p>
              <p className="text-2xl font-bold" style={{
                color: (coverage?.enrichment_rate ?? 0) >= 80 ? '#34d399' : (coverage?.enrichment_rate ?? 0) >= 50 ? '#fbbf24' : '#f87171'
              }}>{coverage?.enrichment_rate ?? 0}%</p>
              <div className="h-1 rounded-full mt-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <div className="h-full rounded-full" style={{
                  width: `${Math.min(100, coverage?.enrichment_rate ?? 0)}%`,
                  background: '#818cf8',
                }} />
              </div>
              <p className="text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.2)' }}>
                {coverage?.enriched_articles_7d ?? 0} / {coverage?.total_articles_7d ?? 0} articles
              </p>
            </div>

            {/* Affiliation */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.3)' }}>Affiliation</p>
              <p className="text-2xl font-bold" style={{
                color: (coverage?.affiliation_rate ?? 0) >= 60 ? '#34d399' : (coverage?.affiliation_rate ?? 0) >= 30 ? '#fbbf24' : '#f87171'
              }}>{coverage?.affiliation_rate ?? 0}%</p>
              <div className="h-1 rounded-full mt-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <div className="h-full rounded-full" style={{
                  width: `${Math.min(100, coverage?.affiliation_rate ?? 0)}%`,
                  background: (coverage?.affiliation_rate ?? 0) >= 60 ? '#34d399' : '#fbbf24',
                }} />
              </div>
              <p className="text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.2)' }}>
                {coverage?.affiliated_articles_7d ?? 0} articles → affaires
              </p>
            </div>

            {/* Radio */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.3)' }}>Radio</p>
              <p className="text-2xl font-bold" style={{ color: '#c084fc' }}>{coverage?.radio_rate ?? 0}%</p>
              <div className="h-1 rounded-full mt-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <div className="h-full rounded-full" style={{
                  width: `${Math.min(100, coverage?.radio_rate ?? 0)}%`,
                  background: '#c084fc',
                }} />
              </div>
              <p className="text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.2)' }}>
                {coverage?.processed_transcriptions_7d ?? 0} / {coverage?.total_transcriptions_7d ?? 0} transcriptions
              </p>
            </div>
          </div>

          {/* ── ROW 2 : Coverage rings + Gravity quality + Trends ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">

            {/* Coverage rings */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-5" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Taux de couverture
              </h2>
              <div className="flex items-center justify-around">
                <ProgressRing pct={coverage?.enrichment_rate ?? 0} color="#818cf8" label="Enrichi" />
                <ProgressRing pct={coverage?.affiliation_rate ?? 0}
                  color={(coverage?.affiliation_rate ?? 0) >= 60 ? '#34d399' : '#fbbf24'} label="Affilié" />
                <ProgressRing pct={coverage?.radio_rate ?? 0} color="#c084fc" label="Radio" />
              </div>
            </div>

            {/* Gravity Quality */}
            <div className="glass-card-static p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Qualité du scoring IA
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full" style={{
                  background: avgGravity <= 0.35 ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
                  color: avgGravity <= 0.35 ? '#34d399' : '#fbbf24',
                }}>moy. {Math.round(avgGravity * 100)}%</span>
              </div>
              {gravDist ? (
                <div className="space-y-3">
                  {[
                    { label: 'Faible (0-25%)', count: gravDist.low, color: '#34d399', target: '~60%' },
                    { label: 'Moyen (25-50%)', count: gravDist.medium, color: '#fbbf24', target: '~25%' },
                    { label: 'Élevé (50-70%)', count: gravDist.high, color: '#fb923c', target: '~10%' },
                    { label: 'Critique (70%+)', count: gravDist.critical, color: '#f87171', target: '~5%' },
                  ].map(seg => {
                    const total = gravDist.low + gravDist.medium + gravDist.high + gravDist.critical
                    const pct = total > 0 ? Math.round(seg.count / total * 100) : 0
                    return (
                      <div key={seg.label}>
                        <div className="flex items-center justify-between mb-0.5">
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: seg.color }} />
                            <span className="text-[11px]" style={{ color: 'rgba(255,255,255,0.5)' }}>{seg.label}</span>
                          </div>
                          <span className="text-[11px]" style={{ color: seg.color }}>
                            {pct}% <span style={{ color: 'rgba(255,255,255,0.15)' }}>cible {seg.target}</span>
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }}>
                          <div className="h-full rounded-full transition-all duration-500" style={{
                            width: `${pct}%`, background: seg.color,
                          }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Pas de données</p>
              )}
            </div>

            {/* Tendances semaine */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Tendances
              </h2>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <div>
                    <p className="text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>Articles cette semaine</p>
                    <p className="text-xl font-bold text-white">{trends?.articles_this_week ?? 0}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>sem. précédente</p>
                    <p className="text-sm" style={{ color: 'rgba(255,255,255,0.4)' }}>{trends?.articles_last_week ?? 0}</p>
                    {trends && (
                      <div className="mt-1 flex items-center justify-end gap-1">
                        <span className="text-xs font-medium" style={{
                          color: trends.articles_trend_pct >= 0 ? '#34d399' : '#f87171'
                        }}>
                          {trends.articles_trend_pct >= 0 ? '+' : ''}{trends.articles_trend_pct}%
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <div>
                    <p className="text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>Affaires créées</p>
                    <p className="text-xl font-bold" style={{ color: '#818cf8' }}>{trends?.affairs_created_this_week ?? 0}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>sem. précédente</p>
                    <p className="text-sm" style={{ color: 'rgba(255,255,255,0.4)' }}>{trends?.affairs_created_last_week ?? 0}</p>
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <div>
                    <p className="text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>BMG moyen</p>
                    <div className="flex items-center gap-2">
                      <BmgGauge value={avgBmg * 100} size={36} />
                      <p className="text-lg font-bold text-white">{Math.round(avgBmg * 100)}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>priorités</p>
                    <div className="flex items-center gap-1.5 mt-1">
                      {(priorityCounts.hot || 0) > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>
                          {priorityCounts.hot}
                        </span>
                      )}
                      {(priorityCounts.watch || 0) > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24' }}>
                          {priorityCounts.watch}
                        </span>
                      )}
                      {(priorityCounts.minor || 0) > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(16,185,129,0.15)', color: '#34d399' }}>
                          {priorityCounts.minor}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ── ROW 3 : Pipeline détaillé + Réconciliation + Index ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">

            {/* Pipeline détaillé */}
            <div className="glass-card-static p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.4)' }}>Pipeline détaillé</h2>
                <StatusDot ok={health?.status === 'healthy'} />
              </div>
              <div>
                <MetricRow label="Candidats total" value={health?.candidates_total ?? '—'} />
                <MetricRow label="Non classés" value={health?.candidates_unclustered ?? '—'} color="#fbbf24" />
                <MetricRow label="Clusters actifs" value={health?.clusters_active ?? '—'} color="#c084fc" />
                <MetricRow label="Affaires actives" value={health?.affairs_active ?? '—'} color="#34d399" />
                <MetricRow label="En veille" value={health?.affairs_stale ?? '—'} color="rgba(255,255,255,0.35)" />
              </div>
              <button onClick={() => handleAction('cycle', () => runFullCycle())} disabled={actionLoading === 'cycle'}
                className="mt-4 w-full py-2 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                style={{ background: 'rgba(16,185,129,0.15)', color: '#34d399', border: '1px solid rgba(16,185,129,0.2)' }}>
                {actionLoading === 'cycle' ? '⟳ Cycle en cours...' : '▶ Lancer le cycle complet'}
              </button>
            </div>

            {/* Réconciliation */}
            <div className="glass-card-static p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.4)' }}>Réconciliation</h2>
                <StatusDot ok={!!reconHealth} />
              </div>
              {reconHealth ? (
                <div>
                  {Object.entries(reconHealth).slice(0, 7).map(([key, val]) => (
                    <MetricRow key={key}
                      label={key.replace(/_/g, ' ')}
                      value={typeof val === 'object' ? JSON.stringify(val).slice(0, 25) : String(val)} />
                  ))}
                </div>
              ) : (
                <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.3)' }}>Service non disponible</p>
              )}
              <div className="flex gap-2 mt-4">
                <button onClick={() => handleAction('recon', () => runReconciliation(3, false))} disabled={!!actionLoading}
                  className="flex-1 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
                  style={{ background: 'rgba(168,85,247,0.15)', color: '#c084fc', border: '1px solid rgba(168,85,247,0.2)' }}>
                  {actionLoading === 'recon' ? '⟳...' : 'Réconcilier'}
                </button>
                <button onClick={() => handleAction('recon_dry', () => runReconciliation(3, true))} disabled={!!actionLoading}
                  className="flex-1 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
                  style={{ background: 'rgba(251,191,36,0.1)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.15)' }}>
                  {actionLoading === 'recon_dry' ? '⟳...' : 'Dry run'}
                </button>
              </div>
            </div>

            {/* Index articles */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>Index articles</h2>
              {indexStatus ? (
                <>
                  <MetricRow label="Articles indexés" value={indexStatus.index_size ?? '—'} />
                  <MetricRow label="Âge index" value={indexStatus.index_age_minutes ? `${indexStatus.index_age_minutes} min` : '—'} />
                  <MetricRow label="Entités uniques" value={indexStatus.unique_entities ?? '—'} color="#c084fc" />
                  <MetricRow label="Affaires dans index" value={indexStatus.affairs_in_index ?? '—'} color="#34d399" />

                  {indexStatus.themes_distribution && (
                    <div className="mt-3 pt-3" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                      <p className="text-[10px] uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.25)' }}>Thèmes</p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(indexStatus.themes_distribution as Record<string, number>)
                          .sort(([, a], [, b]) => (b as number) - (a as number))
                          .slice(0, 8)
                          .map(([theme, count]) => (
                            <span key={theme} className="text-[10px] px-2 py-0.5 rounded-full"
                              style={{ background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.35)' }}>
                              {theme} ({count as number})
                            </span>
                          ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.3)' }}>Index non disponible</p>
              )}
            </div>
          </div>

          {/* ── ROW 4 : Sentiment + Sources + Entités ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">

            {/* Sentiment */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Sentiment médias 7j
              </h2>
              {Object.keys(sentDist).length > 0 ? (
                <div className="space-y-3">
                  {Object.entries(sentDist).map(([key, count]) => {
                    const total = Object.values(sentDist).reduce((s, c) => s + c, 0)
                    const pct = total > 0 ? Math.round(count / total * 100) : 0
                    const colorMap: Record<string, string> = {
                      positif: '#34d399', positive: '#34d399',
                      négatif: '#f87171', negatif: '#f87171', negative: '#f87171',
                      neutre: '#818cf8', neutral: '#818cf8',
                      mixte: '#fbbf24', mixed: '#fbbf24',
                    }
                    const color = colorMap[key.toLowerCase()] || '#94a3b8'
                    return (
                      <div key={key}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[11px] capitalize" style={{ color: 'rgba(255,255,255,0.5)' }}>{key}</span>
                          <span className="text-[11px] font-medium" style={{ color }}>
                            {count} <span style={{ color: 'rgba(255,255,255,0.2)' }}>({pct}%)</span>
                          </span>
                        </div>
                        <div className="h-2 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }}>
                          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Pas de données</p>
              )}
            </div>

            {/* Top sources */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Volume par source
              </h2>
              {topSources.length > 0 ? (
                <div className="space-y-2.5">
                  {topSources.map((s, i) => {
                    const maxC = topSources[0].count
                    const pct = Math.round(s.count / maxC * 100)
                    return (
                      <div key={i}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[11px] truncate" style={{ color: 'rgba(255,255,255,0.5)' }}>{s.name}</span>
                          <span className="text-[11px] font-medium text-white">{s.count}</span>
                        </div>
                        <div className="h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }}>
                          <div className="h-full rounded-full" style={{
                            width: `${pct}%`,
                            background: `linear-gradient(90deg, #6366f1, #818cf8)`,
                          }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Pas de sources</p>
              )}
            </div>

            {/* Entités les plus citées */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Entités les plus citées
              </h2>
              {topEntities.length > 0 ? (
                <div className="space-y-2">
                  {topEntities.slice(0, 10).map((e, i) => {
                    const maxC = topEntities[0].count
                    return (
                      <div key={i} className="flex items-center gap-2">
                        <span className="text-[10px] w-4 text-right" style={{
                          color: i < 3 ? '#fbbf24' : 'rgba(255,255,255,0.2)',
                          fontWeight: i < 3 ? 600 : 400,
                        }}>{i + 1}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="text-[11px] truncate" style={{ color: 'rgba(255,255,255,0.55)' }}>{e.name}</span>
                            <span className="text-[10px] font-medium" style={{ color: 'rgba(255,255,255,0.3)' }}>×{e.count}</span>
                          </div>
                          <div className="h-0.5 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }}>
                            <div className="h-full rounded-full" style={{
                              width: `${(e.count / maxC) * 100}%`,
                              background: i < 3 ? '#c084fc' : 'rgba(168,85,247,0.3)',
                            }} />
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Aucune entité</p>
              )}
            </div>
          </div>

          {/* ── Spinner ── */}
          {actionLoading && (
            <div className="fixed bottom-6 right-6 flex items-center gap-2 px-4 py-2 rounded-xl"
              style={{ background: 'rgba(16,185,129,0.15)', border: '1px solid rgba(16,185,129,0.3)' }}>
              <svg className="w-4 h-4 animate-spin" style={{ color: '#34d399' }} fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              <span className="text-xs font-medium" style={{ color: '#34d399' }}>Action en cours...</span>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
