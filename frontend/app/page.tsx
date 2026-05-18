'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import Link from 'next/link'
import Sidebar from '../components/Sidebar'
import {
  fetchEnrichedDashboard,
  fetchAffairsByCommune,
  fetchStorageStats,
  fetchMapData,
  fetchSearch,
  runFullCycle,
  runReaffiliate,
  runScrapeNow,
  runBulkEnrich,
  fetchSummary,
  fetchRadioHealth,
  fetchRadioToday,
  triggerRadioCapture,
  type EnrichedDashboardData,
  type Affair,
  type DailyActivity,
  type TopEntity,
  type TopSource,
  type OrphanArticle,
  type TimelineEvent,
  type StorageStats,
  type MapResponse,
  type SearchResult,
  type SummaryResponse,
  type MediaSummary,
} from '../lib/api'
import { TopPersonalities } from './_components/dashboard/TopPersonalities'
import { MapboxFullMap } from './_components/dashboard/MapboxFullMap'
import { DashboardTopbar } from './_components/dashboard/DashboardTopbar'
import { KpiStrip } from './_components/dashboard/KpiStrip'
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
  const [cycleRunning, setCycleRunning] = useState(false)
  const [scraping, setScraping] = useState(false)
  const [reaffiliating, setReaffiliating] = useState(false)
  const [bulkEnriching, setBulkEnriching] = useState(false)
  const [bulkMsg, setBulkMsg] = useState('')
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [communeMapData, setCommuneMapData] = useState<Record<string, { count: number; maxGravity: number; affairs: Array<{ _id: string; title: string; gravity_score: number; sentiment: string; theme: string }> }>>({})
  const [selectedCommune, setSelectedCommune] = useState<string | null>(null)
  const [storageStats, setStorageStats] = useState<StorageStats | null>(null)
  const [mapBgData, setMapBgData] = useState<Record<string, { stats: { total_items: number; max_gravity: number } }>>({})

  // ── Search state ──
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const searchTimeout = useRef<NodeJS.Timeout | null>(null)

  // ── Summary state ──
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [summaryData, setSummaryData] = useState<SummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryPeriod, setSummaryPeriod] = useState<'journalier' | 'hebdomadaire'>('journalier')

  // ── Map filters ──
  const [mapFilterTheme, setMapFilterTheme] = useState<string>('all')
  const [mapFilterGravity, setMapFilterGravity] = useState<string>('all')

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

  // ── Radio state ──
  const [radioHealth, setRadioHealth] = useState<Array<{ key: string; name: string; status: string; latency_ms: number }>>([])
  const [radioToday, setRadioToday] = useState<{ count: number; cards: Array<Record<string, unknown>> }>({ count: 0, cards: [] })
  const [radioCapturing, setRadioCapturing] = useState<string | null>(null)
  const [radioPanelOpen, setRadioPanelOpen] = useState(false)
  const [radioCaptureDuration, setRadioCaptureDuration] = useState(60)

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

  const handleRadioCapture = useCallback(async (streamKey: string) => {
    setRadioCapturing(streamKey)
    try {
      await triggerRadioCapture(streamKey, radioCaptureDuration)
      await loadRadioStatus()
    } catch (e) {
      console.error('Radio capture error:', e)
    } finally {
      setRadioCapturing(null)
    }
  }, [loadRadioStatus, radioCaptureDuration])

  useEffect(() => { loadRadioStatus() }, [loadRadioStatus])

  const handleSearch = useCallback((q: string) => {
    setSearchQuery(q)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)
    if (!q.trim() || q.trim().length < 2) {
      setSearchResults(null)
      setSearchOpen(false)
      return
    }
    setSearching(true)
    searchTimeout.current = setTimeout(async () => {
      try {
        const res = await fetchSearch(q.trim())
        setSearchResults(res)
        setSearchOpen(true)
      } catch { setSearchResults(null) }
      finally { setSearching(false) }
    }, 400)
  }, [])

  const loadData = useCallback(async () => {
    try {
      const [result, mapRes, storageRes, mapBgRes] = await Promise.all([
        fetchEnrichedDashboard(),
        fetchAffairsByCommune().catch(() => ({ communes: {} })),
        fetchStorageStats().catch(() => null),
        fetchMapData(7).catch(() => null),
      ])
      setData(result)
      setCommuneMapData(mapRes.communes || {})
      if (storageRes) setStorageStats(storageRes)
      if (mapBgRes?.communes) setMapBgData(mapBgRes.communes as any)
      setError('')
      setLastRefresh(new Date())

      // Check for new hot affairs
      if (data && result) {
        const oldHot = data.top_affairs?.filter((a: any) => a.priority === 'hot').length || 0
        const newHot = result.top_affairs?.filter((a: any) => a.priority === 'hot').length || 0
        if (newHot > oldHot) {
          addNotification(`${newHot - oldHot} nouvelle(s) affaire(s) urgente(s) détectée(s)`, 'hot')
        }
      }
    } catch (e: unknown) {
      setError((e as Error).message || 'Erreur de connexion')
    } finally { setLoading(false) }
  }, [data, addNotification])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 90_000)
    return () => clearInterval(interval)
  }, [loadData])

  const handleRunCycle = async () => {
    setCycleRunning(true)
    try { await runFullCycle(); await loadData(); addNotification('Cycle terminé avec succès', 'success') }
    catch (e: unknown) { console.error('Cycle error:', e) }
    finally { setCycleRunning(false) }
  }

  const handleScrape = async () => {
    setScraping(true)
    try { await runScrapeNow(); await loadData(); addNotification('Scraping terminé', 'success') }
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

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />

      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <DashboardTopbar
          lastRefresh={lastRefresh}
          onRefresh={loadData}
          onOpenBrief={openBrief}
          refreshing={loading}
          cycleId={cycleId}
        />

        {error && (
          <div
            className="mx-6 lg:mx-8 mt-4 px-4 py-3 text-xs"
            style={{ background: 'var(--crit-soft)', color: 'var(--negative)', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}
          >
            {error}
          </div>
        )}

        <div className="px-6 lg:px-8 py-6 max-w-[1700px] mx-auto flex flex-col gap-5">
          {/* ── KPI STRIP — vue scannable en 2 sec ── */}
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

          {/* ── 2-COL : Carte+Baromètre / Flux+Personnalités ── */}
          <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-5">
            <section className="flex flex-col gap-5 min-w-0">
              {/* Carte — élément signature, 600px de haut */}
              <div
                style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                }}
              >
                <div
                  className="flex items-center justify-between px-4 py-3"
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                >
                  <span
                    className="font-mono text-[10px] uppercase tracking-[0.14em]"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    971 · Carte des événements
                  </span>
                  <span
                    className="font-mono text-[10px]"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {Object.keys(mapBgData || {}).length} communes actives
                  </span>
                </div>
                <div className="relative" style={{ height: 600 }}>
                  <MapboxFullMap communes={mapBgData} onSelectCommune={setSelectedCommune} />
                </div>
              </div>

              {/* Baromètre sous la carte — moins de poids visuel */}
              {loading ? (
                <div className="h-48 flex items-center justify-center text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
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

              <div
                className="flex flex-col"
                style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                }}
              >
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
