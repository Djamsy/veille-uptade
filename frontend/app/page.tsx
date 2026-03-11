'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../components/Sidebar'
import BmgGauge from '../components/BmgGauge'
import {
  fetchEnrichedDashboard,
  runFullCycle,
  runReaffiliate,
  runScrapeNow,
  runFullPipeline,
  runBulkEnrich,
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

function themeColorParts(theme: string): [string, string, string] {
  const map: Record<string, string> = {
    politique: 'rgba(168,85,247,0.15)_#c084fc_rgba(168,85,247,0.3)',
    economie: 'rgba(16,185,129,0.15)_#34d399_rgba(16,185,129,0.3)',
    social: 'rgba(96,165,250,0.15)_#93c5fd_rgba(96,165,250,0.3)',
    environnement: 'rgba(74,222,128,0.15)_#86efac_rgba(74,222,128,0.3)',
    sante: 'rgba(251,113,133,0.15)_#fda4af_rgba(251,113,133,0.3)',
    justice: 'rgba(251,191,36,0.15)_#fde68a_rgba(251,191,36,0.3)',
    securite: 'rgba(248,113,113,0.15)_#fca5a5_rgba(248,113,113,0.3)',
    education: 'rgba(129,140,248,0.15)_#a5b4fc_rgba(129,140,248,0.3)',
    culture: 'rgba(244,114,182,0.15)_#f9a8d4_rgba(244,114,182,0.3)',
    sport: 'rgba(34,211,238,0.15)_#67e8f9_rgba(34,211,238,0.3)',
    infrastructure: 'rgba(251,146,60,0.15)_#fdba74_rgba(251,146,60,0.3)',
  }
  const raw = map[theme] || 'rgba(148,163,184,0.15)_#cbd5e1_rgba(148,163,184,0.3)'
  return raw.split('_') as [string, string, string]
}

function ThemeBadge({ theme }: { theme: string }) {
  const [bg, color, border] = themeColorParts(theme)
  return (
    <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: bg, color, border: `1px solid ${border}` }}>
      {themeLabel(theme)}
    </span>
  )
}

function TrendArrow({ pct }: { pct: number }) {
  if (pct === 0) return <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.3)' }}>—</span>
  const up = pct > 0
  return (
    <span className="text-[10px] font-medium flex items-center gap-0.5" style={{ color: up ? '#34d399' : '#f87171' }}>
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"
        style={{ transform: up ? 'rotate(0)' : 'rotate(180deg)' }}>
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
      </svg>
      {Math.abs(pct)}%
    </span>
  )
}

// ── Mini Activity Chart ─────────────────────────────────
function ActivityChart({ data }: { data: DailyActivity[] }) {
  const maxArticles = Math.max(...data.map(d => d.articles), 1)
  return (
    <div className="flex items-end gap-2 h-28">
      {data.map((d, i) => {
        const h = (d.articles / maxArticles) * 100
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
            <div className="absolute -top-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity
              px-1.5 py-0.5 rounded text-[9px] font-medium whitespace-nowrap z-10"
              style={{ background: 'rgba(99,102,241,0.9)', color: 'white' }}>
              {d.articles} art. · {d.events} evt.
            </div>
            <div className="w-full rounded-t transition-all duration-500"
              style={{
                height: `${Math.max(h, 4)}%`,
                background: d.articles > 0
                  ? `linear-gradient(180deg, #818cf8, #4f46e5)`
                  : 'rgba(255,255,255,0.04)',
                boxShadow: d.articles > 0 ? '0 0 8px rgba(99,102,241,0.3)' : 'none',
              }} />
            <span className="text-[9px] leading-none" style={{ color: 'rgba(255,255,255,0.3)' }}>
              {d.label.split(' ')[0]}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Gravity Donut ─────────────────────────────
function GravityDonut({ distribution }: {
  distribution: { low: number; medium: number; high: number; critical: number }
}) {
  const total = distribution.low + distribution.medium + distribution.high + distribution.critical
  if (total === 0) return <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Pas de données</p>

  const segments = [
    { key: 'low', label: 'Faible', count: distribution.low, color: '#34d399' },
    { key: 'medium', label: 'Moyen', count: distribution.medium, color: '#fbbf24' },
    { key: 'high', label: 'Élevé', count: distribution.high, color: '#fb923c' },
    { key: 'critical', label: 'Critique', count: distribution.critical, color: '#f87171' },
  ]

  // Build arc segments
  const radius = 40
  const cx = 50, cy = 50
  const circumference = 2 * Math.PI * radius
  let offset = 0
  const arcs = segments.filter(s => s.count > 0).map(s => {
    const pct = s.count / total
    const len = pct * circumference
    const arc = { ...s, pct, dasharray: `${len} ${circumference - len}`, dashoffset: -offset }
    offset += len
    return arc
  })

  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 100 100" className="w-24 h-24 flex-shrink-0" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={cx} cy={cy} r={radius} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="12" />
        {arcs.map(a => (
          <circle key={a.key} cx={cx} cy={cy} r={radius} fill="none"
            stroke={a.color} strokeWidth="12"
            strokeDasharray={a.dasharray} strokeDashoffset={a.dashoffset}
            strokeLinecap="butt" />
        ))}
        <text x={cx} y={cy + 4} textAnchor="middle" fill="white" fontSize="16" fontWeight="bold"
          style={{ transform: 'rotate(90deg)', transformOrigin: '50% 50%' }}>
          {total}
        </text>
      </svg>
      <div className="space-y-1.5 flex-1">
        {segments.map(s => (
          <div key={s.key} className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
            <span className="text-[11px] flex-1" style={{ color: 'rgba(255,255,255,0.5)' }}>{s.label}</span>
            <span className="text-[11px] font-medium" style={{ color: s.color }}>
              {s.count} <span style={{ color: 'rgba(255,255,255,0.2)' }}>({total > 0 ? Math.round(s.count / total * 100) : 0}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Sentiment bars ──────────────────────────
function SentimentBars({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data)
  if (entries.length === 0) return <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Pas de données</p>
  const total = entries.reduce((s, [, c]) => s + c, 0)
  const colorMap: Record<string, string> = {
    positif: '#34d399', positive: '#34d399',
    négatif: '#f87171', negatif: '#f87171', negative: '#f87171',
    neutre: '#818cf8', neutral: '#818cf8',
    mixte: '#fbbf24', mixed: '#fbbf24',
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, count]) => {
        const color = colorMap[key.toLowerCase()] || '#94a3b8'
        const pct = total > 0 ? Math.round(count / total * 100) : 0
        return (
          <div key={key}>
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[11px] capitalize" style={{ color: 'rgba(255,255,255,0.5)' }}>{key}</span>
              <span className="text-[11px] font-medium" style={{ color }}>{pct}%</span>
            </div>
            <div className="h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }}>
              <div className="h-full rounded-full transition-all duration-700" style={{
                width: `${pct}%`,
                background: color,
                boxShadow: `0 0 6px ${color}40`,
              }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Skeleton ────────────────────────────────
function SkeletonCard() {
  return (
    <div className="glass-card-static p-5">
      <div className="skeleton h-4 w-24 mb-3" />
      <div className="skeleton h-8 w-16 mb-2" />
      <div className="skeleton h-3 w-20" />
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
  const [scraping, setScraping] = useState(false)
  const [reaffiliating, setReaffiliating] = useState(false)
  const [bulkEnriching, setBulkEnriching] = useState(false)
  const [bulkMsg, setBulkMsg] = useState('')
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

  const handleScrape = async () => {
    setScraping(true)
    try { await runScrapeNow(); await loadData() }
    catch (e: unknown) { console.error('Scrape error:', e) }
    finally { setScraping(false) }
  }

  const handleReaffiliate = async () => {
    setReaffiliating(true)
    try { await runReaffiliate(); await loadData() }
    catch (e: unknown) { console.error('Reaffiliate error:', e) }
    finally { setReaffiliating(false) }
  }

  const handleBulkEnrich = async () => {
    setBulkEnriching(true)
    setBulkMsg('')
    try {
      const res = await runBulkEnrich(200, 90)
      setBulkMsg(res.message || `${res.enriched} enrichis`)
      await loadData()
    } catch (e: unknown) { console.error('Bulk enrich error:', e); setBulkMsg('Erreur') }
    finally { setBulkEnriching(false) }
  }

  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-64 flex-1 p-8 min-h-screen">
          <div className="max-w-7xl mx-auto">
            <div className="skeleton h-8 w-48 mb-8" />
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
              {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="glass-card-static p-5"><div className="skeleton h-4 w-32 mb-4" /><div className="skeleton h-28 w-full" /></div>
              ))}
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
  const gravityDist = data?.gravity_distribution
  const sentimentDist = data?.sentiment_distribution || {}
  const priorityCounts = data?.priority_counts || {}
  const trends = data?.trends
  const avgBmg = data?.avg_bmg || 0
  const avgGravity = data?.avg_gravity || 0

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Tableau de bord</h1>
              <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
                MAJ : {lastRefresh.toLocaleTimeString('fr-FR')} — 7 derniers jours
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={loadData} className="btn-glass px-3 py-1.5 text-xs">↻ Rafraîchir</button>
              <button onClick={handleScrape} disabled={scraping} className="btn-glass px-3 py-1.5 text-xs disabled:opacity-50"
                style={scraping ? { background: 'rgba(99,102,241,0.15)', borderColor: 'rgba(99,102,241,0.3)' } : {}}>
                {scraping ? '⟳ Scraping...' : '🌐 Scraper'}
              </button>
              <button onClick={handleBulkEnrich} disabled={bulkEnriching} className="btn-glass px-3 py-1.5 text-xs disabled:opacity-50"
                style={bulkEnriching ? { background: 'rgba(234,179,8,0.15)', borderColor: 'rgba(234,179,8,0.3)' } : {}}
                title="Enrichir massivement les articles non analysés">
                {bulkEnriching ? '⟳ Enrichissement...' : '🧠 Enrichir tout'}
              </button>
              <button onClick={handleRunCycle} disabled={cycleRunning} className="btn-primary px-4 py-1.5 text-xs">
                {cycleRunning ? '⟳ Cycle...' : '▶ Lancer le cycle'}
              </button>
            </div>
            {bulkMsg && (
              <div className="text-xs mt-1 text-right" style={{ color: 'rgba(234,179,8,0.7)' }}>{bulkMsg}</div>
            )}
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
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" style={{ boxShadow: '0 0 8px rgba(239,68,68,0.5)' }} />
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#f87171' }}>Alertes ({criticals.length})</h2>
              </div>
              <div className="space-y-1.5">
                {criticals.slice(0, 3).map((a) => (
                  <Link key={a._id} href={`/affairs/${a._id}`}>
                    <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl cursor-pointer transition-all"
                      style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
                      <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse flex-shrink-0" style={{ boxShadow: '0 0 8px rgba(239,68,68,0.5)' }} />
                      <p className="text-sm font-medium text-white truncate flex-1">{a.title || a.primary_entity}</p>
                      <span className="text-xs font-medium flex-shrink-0" style={{ color: '#f87171' }}>BMG {Math.round((a.bmg || 0) * 100)}</span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* ── ROW 1 : KPI Cards avec tendances ─────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
            {/* Affaires actives */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Affaires actives</p>
              <p className="text-3xl font-bold" style={{ color: '#818cf8' }}>{stats?.affairs_active ?? 0}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{stats?.affairs_stale ?? 0} en veille</span>
              </div>
              {/* Priority mini-dots */}
              <div className="flex items-center gap-2 mt-2">
                {(priorityCounts.hot || 0) > 0 && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>
                    {priorityCounts.hot} urgente{(priorityCounts.hot || 0) > 1 ? 's' : ''}
                  </span>
                )}
                {(priorityCounts.watch || 0) > 0 && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24' }}>
                    {priorityCounts.watch} watch
                  </span>
                )}
              </div>
            </div>

            {/* Articles 7j */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Articles 7j</p>
              <div className="flex items-baseline gap-2">
                <p className="text-3xl font-bold text-white">{coverage?.total_articles_7d ?? 0}</p>
                {trends && <TrendArrow pct={trends.articles_trend_pct} />}
              </div>
              <p className="text-[10px] mt-0.5" style={{ color: 'rgba(255,255,255,0.2)' }}>
                {coverage?.enriched_articles_7d ?? 0} enrichis · {trends?.articles_last_week ?? 0} sem. préc.
              </p>
            </div>

            {/* Taux affiliation */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Affiliation</p>
              <p className="text-3xl font-bold" style={{
                color: (coverage?.affiliation_rate ?? 0) >= 60 ? '#34d399' : (coverage?.affiliation_rate ?? 0) >= 30 ? '#fbbf24' : '#f87171'
              }}>{coverage?.affiliation_rate ?? 0}%</p>
              <div className="h-1 rounded-full mt-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <div className="h-full rounded-full transition-all duration-700" style={{
                  width: `${Math.min(100, coverage?.affiliation_rate ?? 0)}%`,
                  background: (coverage?.affiliation_rate ?? 0) >= 60 ? '#34d399' : (coverage?.affiliation_rate ?? 0) >= 30 ? '#fbbf24' : '#f87171',
                }} />
              </div>
              <p className="text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.2)' }}>{coverage?.affiliated_articles_7d ?? 0} / {coverage?.total_articles_7d ?? 0} affiliés</p>
            </div>

            {/* BMG Moyen */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>BMG moyen</p>
              <div className="flex items-center gap-2">
                <BmgGauge value={avgBmg * 100} size={48} />
                <div>
                  <p className="text-xl font-bold text-white">{Math.round(avgBmg * 100)}</p>
                  <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>/ 100</p>
                </div>
              </div>
            </div>

            {/* Radio */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Radio 7j</p>
              <p className="text-3xl font-bold" style={{ color: '#c084fc' }}>{coverage?.total_transcriptions_7d ?? 0}</p>
              <div className="h-1 rounded-full mt-2" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <div className="h-full rounded-full" style={{
                  width: `${Math.min(100, coverage?.radio_rate ?? 0)}%`,
                  background: '#c084fc',
                }} />
              </div>
              <p className="text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.2)' }}>{coverage?.radio_rate ?? 0}% traitées</p>
            </div>
          </div>

          {/* ── ROW 2 : Charts row (Activité + Gravité + Sentiment) ─── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {/* Activité 7 jours */}
            <div className="glass-card-static p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.4)' }}>Activité 7 jours</h2>
                {trends && (
                  <div className="flex items-center gap-1">
                    <TrendArrow pct={trends.articles_trend_pct} />
                    <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>vs sem. préc.</span>
                  </div>
                )}
              </div>
              {activity.length > 0 ? (
                <>
                  <ActivityChart data={activity} />
                  <div className="flex items-center gap-4 mt-3 justify-center">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full" style={{ background: '#6366f1' }} />
                      <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.3)' }}>Articles</span>
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-xs text-center py-8" style={{ color: 'rgba(255,255,255,0.25)' }}>Pas de données</p>
              )}
            </div>

            {/* Distribution gravité */}
            <div className="glass-card-static p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.4)' }}>Gravité des articles</h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full" style={{
                  background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.35)',
                }}>moy. {Math.round(avgGravity * 100)}%</span>
              </div>
              {gravityDist ? (
                <GravityDonut distribution={gravityDist} />
              ) : (
                <p className="text-xs text-center py-8" style={{ color: 'rgba(255,255,255,0.25)' }}>Pas de données</p>
              )}
            </div>

            {/* Sentiment */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>Sentiment médias</h2>
              <SentimentBars data={sentimentDist} />
            </div>
          </div>

          {/* ── ROW 3 : Thèmes + Sources + Entités ────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {/* Thèmes des affaires */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.4)' }}>Thèmes des affaires</h2>
              {Object.keys(themes).length > 0 ? (
                <div className="space-y-2.5">
                  {Object.entries(themes).map(([theme, count]) => {
                    const maxCount = Math.max(...Object.values(themes))
                    const [, color] = themeColorParts(theme)
                    return (
                      <div key={theme}>
                        <div className="flex items-center justify-between mb-0.5">
                          <ThemeBadge theme={theme} />
                          <span className="text-[11px] font-medium" style={{ color }}>{count}</span>
                        </div>
                        <div className="h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }}>
                          <div className="h-full rounded-full transition-all duration-500" style={{
                            width: `${(count / maxCount) * 100}%`,
                            background: color,
                            boxShadow: `0 0 6px ${color}30`,
                          }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Aucune affaire active</p>
              )}
            </div>

            {/* Sources actives */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.4)' }}>Sources actives 7j</h2>
              {sources.length > 0 ? (
                <div className="space-y-2">
                  {sources.map((s, i) => {
                    const maxC = sources[0].count
                    return (
                      <div key={i}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[11px] truncate" style={{ color: 'rgba(255,255,255,0.5)' }}>{s.name}</span>
                          <span className="text-[11px] font-medium text-white">{s.count}</span>
                        </div>
                        <div className="h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }}>
                          <div className="h-full rounded-full" style={{
                            width: `${(s.count / maxC) * 100}%`,
                            background: 'linear-gradient(90deg, #6366f1, #818cf8)',
                          }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Aucune source</p>
              )}
            </div>

            {/* Top entités */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.4)' }}>Top entités</h2>
              {entities.length > 0 ? (
                <div className="space-y-1.5">
                  {entities.slice(0, 12).map((e, i) => {
                    const maxC = entities[0].count
                    return (
                      <div key={i} className="flex items-center gap-2">
                        <span className="text-[10px] w-4 text-right font-medium" style={{ color: 'rgba(255,255,255,0.2)' }}>{i + 1}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] truncate" style={{ color: 'rgba(255,255,255,0.55)' }}>{e.name}</span>
                            <span className="text-[10px] ml-2 flex-shrink-0" style={{ color: 'rgba(255,255,255,0.25)' }}>×{e.count}</span>
                          </div>
                          <div className="h-0.5 rounded-full mt-0.5" style={{ background: 'rgba(255,255,255,0.04)' }}>
                            <div className="h-full rounded-full" style={{
                              width: `${(e.count / maxC) * 100}%`,
                              background: 'rgba(168,85,247,0.5)',
                            }} />
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.25)' }}>Aucune entité</p>
              )}
            </div>
          </div>

          {/* ── ROW 4 : Top affaires ──────────────── */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white">Affaires majeures</h2>
              <Link href="/affairs" className="text-xs transition-colors" style={{ color: '#818cf8' }}>Voir tout →</Link>
            </div>
            {topAffairs.length === 0 ? (
              <div className="glass-card-static p-10 text-center">
                <p className="text-sm" style={{ color: 'rgba(255,255,255,0.35)' }}>Aucune affaire active</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                {topAffairs.slice(0, 8).map((affair) => {
                  const priority = affair.priority || 'minor'
                  const borderColor = priority === 'hot' ? '#f87171' : priority === 'watch' ? '#fbbf24' : '#34d399'
                  return (
                    <Link key={affair._id} href={`/affairs/${affair._id}`}>
                      <div className="glass-card p-4 cursor-pointer card-hover h-full" style={{ borderLeft: `2px solid ${borderColor}` }}>
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="flex-1 min-w-0">
                            <h3 className="text-sm font-semibold text-white truncate">{affair.title || affair.primary_entity || 'Affaire'}</h3>
                            {affair.primary_entity && affair.title !== affair.primary_entity && (
                              <p className="text-[10px] truncate mt-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>{affair.primary_entity}</p>
                            )}
                          </div>
                          <BmgGauge value={(affair.bmg || 0) * 100} size={48} />
                        </div>
                        <div className="flex flex-wrap gap-1 mb-2">
                          <ThemeBadge theme={affair.theme} />
                          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                            style={{ background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)' }}>
                            {affair.item_count || 0} items
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                          <span>Gravité {Math.round((affair.gravity_score || 0) * 100)}%</span>
                          <span>{timeAgo(affair.last_activity || affair.created_at)}</span>
                        </div>
                      </div>
                    </Link>
                  )
                })}
              </div>
            )}
          </div>

          {/* ── ROW 5 : Orphelins + Timeline ──────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {/* Articles orphelins */}
            <div className="lg:col-span-2">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h2 className="text-sm font-semibold text-white">Articles non affiliés</h2>
                  <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>Enrichis mais sans affaire — à surveiller</p>
                </div>
                <div className="flex items-center gap-2">
                  {orphans.length > 0 && (
                    <span className="text-xs px-2 py-1 rounded-full" style={{
                      background: 'rgba(245,158,11,0.1)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.2)'
                    }}>{orphans.length} orphelins</span>
                  )}
                  <button onClick={handleReaffiliate} disabled={reaffiliating} className="btn-glass text-xs px-3 py-1 disabled:opacity-50">
                    {reaffiliating ? '⟳ En cours...' : '🔗 Ré-affilier'}
                  </button>
                </div>
              </div>
              {orphans.length > 0 ? (
                <div className="glass-card-static overflow-hidden">
                  {orphans.map((art, idx) => (
                    <div key={art._id} className="flex items-center gap-3 px-4 py-2.5"
                      style={{ borderBottom: idx < orphans.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                      <ThemeBadge theme={art.theme} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs truncate" style={{ color: 'rgba(255,255,255,0.6)' }}>{art.title}</p>
                        <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>{art.source} — {timeAgo(art.scraped_at)}</p>
                      </div>
                      <div className="flex-shrink-0 text-right">
                        <p className="text-xs font-bold" style={{
                          color: art.gravity_score >= 0.7 ? '#f87171' : art.gravity_score >= 0.4 ? '#fbbf24' : 'rgba(255,255,255,0.3)'
                        }}>{Math.round(art.gravity_score * 100)}%</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="glass-card-static p-6 text-center">
                  <p className="text-xs" style={{ color: 'rgba(255,255,255,0.25)' }}>Tous les articles sont affiliés</p>
                </div>
              )}
            </div>

            {/* Timeline */}
            <div className="glass-card-static p-4">
              <h3 className="text-[10px] uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.3)' }}>Activité récente</h3>
              {timeline.length > 0 ? (
                <div className="space-y-2">
                  {timeline.slice(0, 10).map((evt) => {
                    const iconMap: Record<string, string> = {
                      created: '🆕', article_added: '📰', radio_topic_added: '📻',
                      gravity_update: '📊', archived: '📦', expired: '⏰', bmg_change: '📈',
                    }
                    return (
                      <div key={evt._id} className="flex items-start gap-2 py-1">
                        <span className="text-xs flex-shrink-0">{iconMap[evt.event] || '•'}</span>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs truncate" style={{ color: 'rgba(255,255,255,0.5)' }}>
                            {(evt.details as Record<string, string>)?.title ||
                             (evt.details as Record<string, string>)?.reason ||
                             evt.event}
                          </p>
                          <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{timeAgo(evt.timestamp)}</p>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs py-4 text-center" style={{ color: 'rgba(255,255,255,0.25)' }}>Aucune activité</p>
              )}
            </div>
          </div>

          {/* ── ROW 6 : Pipeline technique ─────────────── */}
          {stats && (
            <div className="glass-card-static p-4">
              <h2 className="text-[10px] uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.3)' }}>Pipeline technique</h2>
              <div className="flex items-center gap-4 overflow-x-auto">
                {[
                  { label: 'Candidats', value: stats.candidates_total, sub: 'Ingestion', color: '#fbbf24', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.2)' },
                  { label: 'Non classés', value: stats.candidates_unclustered, sub: 'En attente', color: '#f87171', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.2)' },
                  { label: 'Clusters', value: stats.clusters_active, sub: 'Groupement', color: '#c084fc', bg: 'rgba(168,85,247,0.1)', border: 'rgba(168,85,247,0.2)' },
                  { label: 'Affaires', value: stats.affairs_active, sub: 'Promues', color: '#818cf8', bg: 'rgba(99,102,241,0.1)', border: 'rgba(99,102,241,0.2)' },
                  { label: 'En veille', value: stats.affairs_stale, sub: 'Archivage', color: 'rgba(255,255,255,0.4)', bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.08)' },
                ].map((step, i, arr) => (
                  <div key={i} className="flex items-center gap-3 flex-shrink-0">
                    <div className="w-9 h-9 rounded-full flex items-center justify-center" style={{ background: step.bg, border: `1px solid ${step.border}` }}>
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
