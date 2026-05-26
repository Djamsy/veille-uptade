'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import Link from 'next/link'
import Sidebar from '../components/Sidebar'
import { GuadeloupeMark } from '../components/GuadeloupeMark'
import GuadeloupeMap from '../components/GuadeloupeMap'
import {
  fetchEnrichedDashboard,
  fetchMapData,
  fetchSummary,
  fetchRadioHealth,
  fetchRadioToday,
  type EnrichedDashboardData,
  type SummaryResponse,
} from '../lib/api'
import { TopPersonalities } from './_components/dashboard/TopPersonalities'
import { MapboxFullMap } from './_components/dashboard/MapboxFullMap'
import { DashboardTopbar } from './_components/dashboard/DashboardTopbar'
import { KpiStrip } from './_components/dashboard/KpiStrip'
import { CollectiviteHero } from './_components/dashboard/CollectiviteHero'
import { LiveFeed } from './_components/dashboard/LiveFeed'
import { BarometreCard } from './_components/dashboard/BarometreCard'
import {
  MOCK_AFFAIRS,
  MOCK_ENTITIES,
  MOCK_ENTITY_META,
  MOCK_ACTIVITY,
  MOCK_SENTIMENT,
  MOCK_KPIS,
} from './_components/dashboard/mocks'

// ════════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ════════════════════════════════════════════════════════════
export default function DashboardPage() {
  const [data, setData] = useState<EnrichedDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [mapBgData, setMapBgData] = useState<Record<string, { stats: { total_items: number; max_gravity: number } }>>({})

  // ── Summary state ──
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [summaryData, setSummaryData] = useState<SummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryPeriod, setSummaryPeriod] = useState<'journalier' | 'hebdomadaire'>('journalier')

  // ── Notifications ──
  const [notifications, setNotifications] = useState<Array<{ id: number; text: string; type: 'hot' | 'info' | 'success' }>>([])
  const notifIdRef = useRef(0)

  const addNotification = useCallback((text: string, type: 'hot' | 'info' | 'success' = 'info') => {
    const id = ++notifIdRef.current
    setNotifications(prev => [...prev.slice(-4), { id, text, type }])
    setTimeout(() => setNotifications(prev => prev.filter(n => n.id !== id)), 5000)
  }, [])

  const handleGenerateSummary = useCallback(async (period: 'journalier' | 'hebdomadaire') => {
    setSummaryLoading(true)
    setSummaryPeriod(period)
    setSummaryOpen(true)
    try {
      const res = await fetchSummary(period)
      setSummaryData(res)
    } catch (e) {
      console.error('Summary error:', e)
    } finally {
      setSummaryLoading(false)
    }
  }, [])

  // ── Radio state (read-only — capture handlers vivent sur /radio) ──
  const [radioHealth, setRadioHealth] = useState<Array<{ key: string; name: string; status: string; latency_ms: number }>>([])
  const [radioToday, setRadioToday] = useState<{ count: number; cards: Array<Record<string, unknown>> }>({ count: 0, cards: [] })

  const loadRadioStatus = useCallback(async () => {
    try {
      const [health, today] = await Promise.all([
        fetchRadioHealth().catch(() => ({ results: [], summary: { total: 0, healthy: 0, degraded: 0, down: 0 }, checked_at: '' })),
        fetchRadioToday().catch(() => ({ cards: [], count: 0 })),
      ])
      setRadioHealth(health.results || [])
      setRadioToday(today)
    } catch { /* silent */ }
  }, [])

  useEffect(() => { loadRadioStatus() }, [loadRadioStatus])

  // hotCount évite la closure stale sur `data` qui forçait loadData à se recréer
  // à chaque setData (recréait le setInterval à chaque tick, cf. ancien S5).
  const prevHotCountRef = useRef(0)

  const loadData = useCallback(async () => {
    try {
      const [result, mapBgRes] = await Promise.all([
        fetchEnrichedDashboard(),
        fetchMapData(7).catch(() => null),
      ])
      setData(result)
      if (mapBgRes?.communes) setMapBgData(mapBgRes.communes as any)
      setError('')
      setLastRefresh(new Date())

      // Détection des nouvelles affaires urgentes via ref (pas de dep cycliques)
      const newHot = result?.top_affairs?.filter((a: any) => a.priority === 'hot').length || 0
      if (newHot > prevHotCountRef.current) {
        addNotification(`${newHot - prevHotCountRef.current} nouvelle(s) affaire(s) urgente(s) détectée(s)`, 'hot')
      }
      prevHotCountRef.current = newHot
    } catch (e: unknown) {
      setError((e as Error).message || 'Erreur de connexion')
    } finally { setLoading(false) }
  }, [addNotification])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 90_000)
    return () => clearInterval(interval)
  }, [loadData])

  const topAffairs = data?.top_affairs || []
  const stats = data?.stats
  const coverage = data?.coverage
  const entities = data?.top_entities || []
  const activity = data?.daily_activity || []
  const sentimentDist = data?.sentiment_distribution || {}
  const priorityCounts = data?.priority_counts || {}
  const trends = data?.trends
  const avgBmg = data?.avg_bmg || 0
  const cycleId = Math.floor(lastRefresh.getTime() / 60000) % 10000

  // ── Mocks fallback (when backend returns nothing) ──
  const liveAffairs = topAffairs.length > 0 ? topAffairs : MOCK_AFFAIRS
  const livePeople = entities.length > 0 ? entities : MOCK_ENTITIES
  const liveActivity = activity.length > 0 ? activity : MOCK_ACTIVITY
  const liveSentiment = Object.keys(sentimentDist).length > 0 ? sentimentDist : MOCK_SENTIMENT
  const liveBmg = (avgBmg > 0 ? avgBmg : MOCK_KPIS.bmg_scaled / 100)
  const liveArticlesDelta = trends?.articles_trend_pct ?? (data ? 0 : MOCK_KPIS.articles_delta_pct)
  const isMockFeed = topAffairs.length === 0
  const isMockPeople = entities.length === 0
  const isMockKpis = !data

  const openBrief = () => {
    handleGenerateSummary(summaryPeriod)
  }

  // Nappe de climat ambiante sur la carte — couleur selon le BMG réel
  const climateWash =
    liveBmg >= 0.6 ? 'rgba(229, 75, 90, 0.18)'   // tendu (Soufrière)
    : liveBmg >= 0.4 ? 'rgba(240, 169, 59, 0.15)' // surveillé (volcan)
    : 'rgba(31, 182, 166, 0.14)'                  // apaisé (turquoise)

  // Verdict de climat (signal réel) pour l'overlay sur la carte
  const bmg100 = Math.round(liveBmg * 100)
  const verdict =
    liveBmg >= 0.6 ? { t: 'Climat tendu', c: 'var(--negative)' }
    : liveBmg >= 0.4 ? { t: 'Sous surveillance', c: 'var(--warning)' }
    : liveBmg >= 0.2 ? { t: 'Climat actif', c: 'var(--caution)' }
    : { t: 'Climat apaisé', c: 'var(--positive)' }

  // Données communes pour la carte SVG (territoire vivant)
  const communeData: Record<string, { count: number; maxGravity: number }> = Object.fromEntries(
    Object.entries(mapBgData || {}).map(([name, d]) => [
      name,
      { count: d?.stats?.total_items ?? 0, maxGravity: d?.stats?.max_gravity ?? 0 },
    ])
  )
  // Fallback démo : allume quelques communes pour montrer le territoire « vivant »
  const MOCK_COMMUNES: Record<string, { count: number; maxGravity: number }> = {
    'Baie-Mahault': { count: 8, maxGravity: 0.78 },
    'Petit-Bourg': { count: 5, maxGravity: 0.58 },
    'Sainte-Rose': { count: 4, maxGravity: 0.42 },
    'Lamentin': { count: 3, maxGravity: 0.32 },
    'Pointe-Noire': { count: 2, maxGravity: 0.5 },
    'Goyave': { count: 3, maxGravity: 0.66 },
  }
  const liveCommuneData = Object.keys(communeData).length > 0 ? communeData : MOCK_COMMUNES
  const communesActives = Object.keys(liveCommuneData).length

  // Vraie carte 3D Mapbox si token présent, sinon carte SVG vectorielle (token-free)
  const hasMapbox = !!process.env.NEXT_PUBLIC_MAPBOX_TOKEN

  return (
    <div className="theme-carte flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />

      <main className="lg:ml-16 flex-1 relative overflow-hidden">
        {/* Ambiance mer — fond fixe derrière le contenu (la carte est inline dans le héros) */}
        <div className="fixed inset-0 lg:left-[220px] z-0 carte-bg" aria-hidden>
          <div className="carte-wash" style={{ ['--climate-wash' as string]: climateWash } as React.CSSProperties} />
        </div>

        {/* ── CONTENU flottant au-dessus de la carte ── */}
        <div className="relative z-10 h-full overflow-y-auto">
          <DashboardTopbar
            lastRefresh={lastRefresh}
            onRefresh={loadData}
            onOpenBrief={openBrief}
            refreshing={loading}
            cycleId={cycleId}
          />

          {error && (
            <div className="mx-6 lg:mx-8 mt-4 px-4 py-3 text-xs glass-panel" style={{ color: 'var(--negative)' }}>
              {error}
            </div>
          )}

          <div className="px-6 lg:px-8 pb-10 pt-2 max-w-[1500px] mx-auto flex flex-col gap-5">
          {/* ═══ HERO : LE TERRITOIRE EST LE DASHBOARD (plein écran immersif) ═══ */}
          <div className="relative reveal reveal-2" style={{ minHeight: 'calc(100vh - 150px)' }}>
            {/* Carte : vraie 3D Mapbox si token présent, sinon SVG vectoriel (token-free) */}
            {hasMapbox ? (
              <div className="absolute inset-0 rounded-2xl overflow-hidden" style={{ border: '1px solid var(--border)' }}>
                <MapboxFullMap communes={mapBgData} />
              </div>
            ) : (
              <div className="absolute inset-0 flex items-center justify-center px-4">
                <div className="relative w-full" style={{ maxWidth: 1080 }}>
                  <GuadeloupeMap communeData={liveCommuneData} />
                </div>
              </div>
            )}

            {/* Overlays — flottent sur la carte (Mapbox ou SVG) */}
            <div className="glass-panel absolute top-6 left-6 p-3.5 w-[44%] max-w-[240px] z-10">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-muted)' }}>Climat média · 7j</div>
              <div className="text-base font-semibold mt-1.5 leading-tight" style={{ color: verdict.c }}>{verdict.t}</div>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-3xl font-semibold tabular-data leading-none" style={{ color: 'var(--text)' }}>{bmg100}</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--text-muted)' }}>BMG moyen</span>
              </div>
            </div>
            <div className="glass-panel absolute top-6 right-6 p-3.5 w-[44%] max-w-[240px] text-right z-10">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-muted)' }}>971 · Territoire</div>
              <div className="flex items-baseline gap-2 mt-1 justify-end">
                <span className="text-3xl font-semibold tabular-data leading-none" style={{ color: 'var(--text)' }}>{communesActives}</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--text-muted)' }}>communes actives</span>
              </div>
              <div className="font-mono text-[10px] mt-1.5" style={{ color: 'var(--text-muted)' }}>Carte en direct</div>
            </div>
          </div>

          {/* ── COLLECTIVITÉ + CLIMAT — réponse prioritaire au job ── */}
          <CollectiviteHero
            avgBmg={liveBmg}
            trendPct={trends?.articles_trend_pct != null ? Math.round(trends.articles_trend_pct) : undefined}
            sentimentDist={liveSentiment}
            isMock={isMockKpis}
          />

          {/* ── KPI STRIP — opérationnel, scannable (secondaire) ── */}
          <div className="reveal reveal-3">
          <KpiStrip
            isMock={isMockKpis}
            kpis={[
              {
                label: 'Affaires actives',
                value: stats?.affairs_active ?? MOCK_KPIS.affairs_active,
                trend: isMockKpis ? { delta: MOCK_KPIS.affairs_delta_pct, period: '%' } : undefined,
              },
              {
                label: 'Urgentes ≥70',
                value: priorityCounts?.hot ?? MOCK_KPIS.urgents,
                trend: isMockKpis ? { delta: MOCK_KPIS.urgents_delta_pct, period: '%' } : undefined,
                severity: ((priorityCounts?.hot ?? MOCK_KPIS.urgents) > 0) ? 'crit' : 'neutral',
              },
              {
                label: 'Articles · 7j',
                value: coverage?.total_articles_7d ?? MOCK_KPIS.articles_7d,
                goodDirection: 'up',
                trend: trends?.articles_trend_pct != null
                  ? { delta: Math.round(trends.articles_trend_pct), period: '%' }
                  : isMockKpis
                    ? { delta: MOCK_KPIS.articles_delta_pct, period: '%' }
                    : undefined,
              },
              {
                label: 'Captures radio · 24h',
                value: radioToday.count > 0
                  ? `${radioToday.count}/${radioHealth.length || 0}`
                  : `${MOCK_KPIS.radio_today}/${MOCK_KPIS.radio_total}`,
                goodDirection: 'up',
              },
            ]}
          />
          </div>

          {/* ── 2-COL : Carte+Baromètre / Flux+Personnalités ── */}
          <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-5 reveal reveal-4">
            <section className="flex flex-col gap-5 min-w-0">
              {/* La carte est désormais le FOND plein écran. Ici : le baromètre. */}
              {loading ? (
                <div className="glass-panel h-48 flex items-center justify-center text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                  Chargement…
                </div>
              ) : (
                <BarometreCard
                  avgBmg={liveBmg}
                  articlesDelta={liveArticlesDelta}
                  activity={liveActivity}
                  sentimentDist={liveSentiment}
                  isMock={isMockKpis}
                />
              )}
            </section>

            {/* ── RIGHT RAIL : Flux + Personnalités ── */}
            <aside className="flex flex-col gap-5 min-w-0">
              <LiveFeed affairs={liveAffairs} isMock={isMockFeed} />

              <div className="glass-panel flex flex-col">
                <div
                  className="flex items-center justify-between px-3.5 py-3"
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                >
                  <span
                    className="font-mono text-[10px] uppercase tracking-[0.14em]"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Personnalités clés
                  </span>
                  <Link
                    href="/affairs"
                    className="text-[10px] font-medium hover:underline"
                    style={{ color: 'var(--accent-link)' }}
                  >
                    Voir tout
                  </Link>
                </div>
                <div className="p-3.5">
                  <TopPersonalities
                    entities={livePeople}
                    meta={isMockPeople ? MOCK_ENTITY_META : undefined}
                  />
                </div>
              </div>
            </aside>
          </div>
        </div>
        </div>

        {/* ── Notifications toast ── */}
        {notifications.length > 0 && (
          <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
            {notifications.map(n => (
              <div
                key={n.id}
                className="animate-slide-up rounded-sm px-4 py-2.5 text-xs font-medium flex items-center gap-2 shadow-md"
                style={{
                  background: n.type === 'hot' ? 'var(--crit-soft)' : n.type === 'success' ? 'var(--ok-soft)' : 'var(--info-soft)',
                  color: n.type === 'hot' ? '#b02939' : n.type === 'success' ? '#3d6f44' : '#2f5680',
                  border: `1px solid ${n.type === 'hot' ? '#f5d4d9' : n.type === 'success' ? '#cce5d0' : '#d3dde9'}`,
                }}
              >
                <span>{n.text}</span>
                <button
                  onClick={() => setNotifications(prev => prev.filter(x => x.id !== n.id))}
                  className="ml-auto opacity-60 hover:opacity-100"
                  aria-label="Fermer"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        {/* ── Brief du jour modal ── */}
        {summaryOpen && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(24,24,27,0.4)', backdropFilter: 'blur(4px)' }}
            onClick={() => setSummaryOpen(false)}
          >
            <div
              className="max-w-2xl w-full max-h-[85vh] overflow-y-auto"
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                boxShadow: 'var(--shadow-elevated)',
              }}
              onClick={e => e.stopPropagation()}
            >
              <div
                className="flex items-center justify-between px-6 py-4"
                style={{ borderBottom: '1px solid var(--border)' }}
              >
                <div>
                  <div
                    className="font-mono text-[10px] uppercase tracking-[0.18em] mb-1 cursor-help"
                    style={{ color: 'var(--text-muted)' }}
                    title="Jou-la (kréyol gwadloupéyen) — aujourd'hui"
                  >
                    Jou-la · Brief
                  </div>
                  <h2 className="font-serif text-xl italic font-medium" style={{ color: 'var(--text)' }}>
                    Résumé {summaryPeriod === 'journalier' ? 'du jour' : 'de la semaine'}
                  </h2>
                </div>
                <button
                  onClick={() => setSummaryOpen(false)}
                  className="text-lg opacity-50 hover:opacity-100"
                  aria-label="Fermer"
                >
                  ✕
                </button>
              </div>
              <div className="p-6">
                {summaryLoading ? (
                  <div className="text-center py-12">
                    <div className="text-2xl animate-spin inline-block mb-3">⟳</div>
                    <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                      Génération du résumé IA en cours…
                    </p>
                  </div>
                ) : summaryData?.summary ? (
                  <div className="space-y-4">
                    <p className="font-serif text-base italic leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                      {summaryData.summary.introduction}
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-center py-8" style={{ color: 'var(--text-muted)' }}>
                    Aucun résumé disponible
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
