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
import { timeAgo, themeLabel, themeColor, themeColorParts } from '../lib/formatters'
import { ThemeBadge } from './_components/dashboard/ThemeBadge'
import { TrendArrow } from './_components/dashboard/TrendArrow'
import { SkeletonCard, SkeletonWidget } from './_components/dashboard/Skeletons'
import { SentimentGauge } from './_components/dashboard/SentimentGauge'
import { TopPersonalities } from './_components/dashboard/TopPersonalities'
import { TrendingTopics } from './_components/dashboard/TrendingTopics'
import { ActivityMiniChart } from './_components/dashboard/ActivityMiniChart'
import { MajorStories } from './_components/dashboard/MajorStories'
import { AffairTimeline } from './_components/dashboard/AffairTimeline'
import { GravityDonut } from './_components/dashboard/GravityDonut'
import { MapboxFullMap } from './_components/dashboard/MapboxFullMap'

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

  // ── Mobile panel toggle (carte vs panneau) ──
  const [mobilePanelOpen, setMobilePanelOpen] = useState(false)

  // ── Theme mode ──
  const [themeMode, setThemeMode] = useState<'dark' | 'light'>('light')

  useEffect(() => {
    const saved = localStorage.getItem('veille-theme') || 'light'
    setThemeMode(saved as 'dark' | 'light')
    document.documentElement.setAttribute('data-theme', saved)
  }, [])

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

  const toggleTheme = useCallback(() => {
    const next = themeMode === 'dark' ? 'light' : 'dark'
    setThemeMode(next)
    document.documentElement.setAttribute('data-theme', next)
    localStorage.setItem('veille-theme', next)
  }, [themeMode])

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

  // Rendre le body + html transparent pour que la carte Mapbox soit visible
  useEffect(() => {
    document.documentElement.style.background = 'transparent'
    document.body.classList.add('map-dashboard-mode')
    document.body.style.background = 'transparent'
    // Aussi forcer le parent Next.js
    const nextRoot = document.getElementById('__next')
    if (nextRoot) nextRoot.style.background = 'transparent'
    // Forcer le wrapper z-10 du layout à être transparent
    const zWrapper = document.querySelector('.relative.z-10') as HTMLElement
    if (zWrapper) zWrapper.style.background = 'transparent'
    return () => {
      document.documentElement.style.background = ''
      document.body.classList.remove('map-dashboard-mode')
      document.body.style.background = ''
      if (nextRoot) nextRoot.style.background = ''
      if (zWrapper) zWrapper.style.background = ''
    }
  }, [])

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

  // ── Panneau style commun ──
  const panelStyle = `rounded-2xl shadow-2xl ${themeMode === 'light' ? 'border border-black/8' : 'border border-white/10'}`
  const panelBg = themeMode === 'light'
    ? { background: 'rgba(255,255,255,0.82)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }
    : { background: 'rgba(2,6,23,0.82)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />

      {/* Zone principale = carte plein écran + widgets flottants */}
      <div className="lg:ml-16 flex-1 relative h-screen overflow-hidden">

        {/* ══ CARTE 3D PLEIN ÉCRAN ══ */}
        <MapboxFullMap communes={mapBgData} onSelectCommune={setSelectedCommune} />

        {/* ══ WIDGETS FLOTTANTS ══ */}
        <div className="absolute inset-0 z-10 pointer-events-none">

          {/* ── TOP BAR: Header + Actions ── */}
          <div className="pointer-events-auto mobile-top-bar absolute top-3 left-3 right-3 flex items-center justify-between gap-2 sm:gap-3">
            <div className={`${panelStyle} px-3 sm:px-4 py-2 sm:py-2.5 flex items-center gap-2 sm:gap-3`} style={panelBg}>
              <h1 className="text-xs sm:text-sm lg:text-base font-bold text-white tracking-tight whitespace-nowrap">Veille 971</h1>
              <span className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold"
                style={{ background: 'rgba(22,163,74,0.15)', color: '#34d399', border: '1px solid rgba(22,163,74,0.3)' }}>
                LIVE
              </span>
              <span className="text-[10px] font-medium" style={{ color: 'rgba(255,255,255,0.3)' }}>
                {lastRefresh.toLocaleTimeString('fr-FR')}
              </span>
            </div>

            {/* ── Search Bar ── */}
            <div className="relative flex-1 max-w-[140px] sm:max-w-xs">
              <div className={`${panelStyle} flex items-center gap-2 px-3 py-1.5`} style={panelBg}>
                <svg className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'rgba(255,255,255,0.4)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="text"
                  placeholder="Rechercher…"
                  value={searchQuery}
                  onChange={e => handleSearch(e.target.value)}
                  onFocus={() => searchResults && setSearchOpen(true)}
                  onBlur={() => setTimeout(() => setSearchOpen(false), 200)}
                  className="bg-transparent border-none outline-none text-xs text-white placeholder-white/30 w-full"
                />
                {searching && <span className="text-[10px] text-cyan-400 animate-pulse">⟳</span>}
                {searchQuery && !searching && (
                  <button onClick={() => { setSearchQuery(''); setSearchResults(null); setSearchOpen(false) }}
                    className="text-white/30 hover:text-white/60 text-xs">✕</button>
                )}
              </div>
              {/* Search Results Dropdown */}
              {searchOpen && searchResults && (searchResults.total_articles > 0 || searchResults.total_affairs > 0) && (
                <div className="absolute top-full mt-1 left-0 right-0 z-50 rounded-xl overflow-hidden shadow-2xl"
                  style={{ background: 'rgba(10,15,30,0.95)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)', maxHeight: '400px', overflowY: 'auto' }}>
                  {searchResults.total_affairs > 0 && (
                    <div className="px-3 pt-2 pb-1">
                      <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(147,197,253,0.6)' }}>
                        Affaires ({searchResults.total_affairs})
                      </p>
                      {searchResults.affairs.slice(0, 5).map(a => (
                        <div key={a._id} className="py-1.5 border-b border-white/5 cursor-pointer hover:bg-white/5 px-1 rounded"
                          onMouseDown={() => { setSelectedCommune(null); setSearchOpen(false) }}>
                          <p className="text-xs text-white/90 font-medium truncate">{a.title}</p>
                          <p className="text-[10px] text-white/40 truncate">{a.theme} · gravité {Math.round((a.gravity_score || 0) * 100)}%</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {searchResults.total_articles > 0 && (
                    <div className="px-3 pt-2 pb-2">
                      <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(253,224,71,0.6)' }}>
                        Articles ({searchResults.total_articles})
                      </p>
                      {searchResults.articles.slice(0, 5).map(a => (
                        <div key={a._id} className="py-1.5 border-b border-white/5 px-1">
                          <p className="text-xs text-white/90 truncate">{a.title}</p>
                          <p className="text-[10px] text-white/40 truncate">{a.source} · {a.date ? new Date(a.date).toLocaleDateString('fr-FR') : ''}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Theme Toggle */}
            <button onClick={toggleTheme} className="btn-glass px-2 py-1.5 rounded-xl text-sm" title={themeMode === 'dark' ? 'Mode clair' : 'Mode sombre'}>
              {themeMode === 'dark' ? '☀️' : '🌙'}
            </button>

            <div className={`${panelStyle} px-3 py-2 flex items-center gap-2`} style={panelBg}>
              <button onClick={() => handleGenerateSummary(summaryPeriod)} disabled={summaryLoading} className="btn-glass px-2.5 py-1 text-[10px] disabled:opacity-40">
                {summaryLoading ? '⟳...' : '📰 Résumé'}
              </button>
              <button onClick={loadData} className="btn-glass px-2.5 py-1 text-[10px]">
                <svg className="w-3 h-3 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                MAJ
              </button>
              <button onClick={handleScrape} disabled={scraping} className="btn-glass px-2.5 py-1 text-[10px] disabled:opacity-40">
                {scraping ? '⟳...' : 'Scraper'}
              </button>
              <button onClick={handleRunCycle} disabled={cycleRunning} className="btn-primary px-3 py-1 text-[10px]">
                {cycleRunning ? '⟳...' : '▶ Cycle'}
              </button>
              <button onClick={() => {
                const url = `${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'}/api/export/csv?type=affairs`
                window.open(url, '_blank')
              }} className="btn-glass px-2.5 py-1 text-[10px]">
                📥 CSV
              </button>
            </div>
          </div>

          {error && (
            <div className="pointer-events-auto absolute top-16 left-3 right-3 px-4 py-2 rounded-xl text-xs z-20" style={{
              background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: '#f87171',
              backdropFilter: 'blur(12px)',
            }}>{error}</div>
          )}

          {/* ── Map Filters ── */}
          <div className="pointer-events-auto absolute top-16 right-3 flex flex-col gap-1.5 z-20">
            <div className={`${panelStyle} px-2.5 py-2 flex flex-col gap-1`} style={panelBg}>
              <p className="text-[8px] uppercase tracking-wider font-semibold opacity-40 mb-0.5">Thème</p>
              {['all', 'politique', 'justice', 'social', 'économie', 'environnement', 'santé'].map(t => (
                <button key={t} onClick={() => setMapFilterTheme(t)}
                  className={`text-[9px] px-2 py-0.5 rounded-lg text-left transition-all ${mapFilterTheme === t ? 'bg-indigo-500/20 text-indigo-300 font-semibold' : 'opacity-50 hover:opacity-80'}`}>
                  {t === 'all' ? 'Tous' : t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <div className={`${panelStyle} px-2.5 py-2 flex flex-col gap-1`} style={panelBg}>
              <p className="text-[8px] uppercase tracking-wider font-semibold opacity-40 mb-0.5">Gravité</p>
              {[
                { key: 'all', label: 'Toutes', color: '' },
                { key: 'critical', label: 'Critique', color: 'text-red-400' },
                { key: 'high', label: 'Élevée', color: 'text-orange-400' },
                { key: 'medium', label: 'Moyenne', color: 'text-yellow-400' },
                { key: 'low', label: 'Faible', color: 'text-green-400' },
              ].map(g => (
                <button key={g.key} onClick={() => setMapFilterGravity(g.key)}
                  className={`text-[9px] px-2 py-0.5 rounded-lg text-left transition-all ${g.color} ${mapFilterGravity === g.key ? 'bg-white/10 font-semibold' : 'opacity-50 hover:opacity-80'}`}>
                  {g.label}
                </button>
              ))}
            </div>
          </div>

          {/* ══ BOUTON TOGGLE MOBILE (carte ↔ panneau) ══ */}
          <button
            className="pointer-events-auto sm:hidden fixed z-30 right-3 shadow-lg"
            onClick={() => setMobilePanelOpen(!mobilePanelOpen)}
            style={{
              bottom: mobilePanelOpen ? 'calc(45vh + 60px)' : '68px',
              background: 'var(--primary)',
              color: '#fff',
              borderRadius: '50%',
              width: '44px',
              height: '44px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'bottom 300ms ease',
              boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
            }}
            aria-label={mobilePanelOpen ? 'Voir la carte' : 'Voir les affaires'}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {mobilePanelOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>

          {/* ══ LEFT PANEL: KPIs + Alertes + Affaires ══ */}
          <div className={`pointer-events-auto dash-left-panel absolute top-16 left-3 bottom-3 w-[calc(100vw-1.5rem)] sm:w-[320px] lg:w-[340px] flex flex-col gap-2 sm:gap-2.5 overflow-y-auto overflow-x-hidden scrollbar-hide ${mobilePanelOpen ? '' : 'mobile-panel-hidden'}`} style={{ maxHeight: 'calc(100vh - 80px)' }}>

            {/* KPI Row */}
            {!loading && stats && (
              <div className="grid grid-cols-2 gap-2">
                <div className={`${panelStyle} p-3`} style={panelBg}>
                  <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(147,197,253,0.7)' }}>Affaires</p>
                  <p className="text-2xl font-bold" style={{ color: '#93c5fd' }}>{stats.affairs_active ?? 0}</p>
                  <div className="flex gap-1 mt-1">
                    {(priorityCounts.hot || 0) > 0 && <span className="text-[8px] px-1.5 py-0.5 rounded-full font-bold" style={{ background: 'rgba(239,68,68,0.2)', color: '#fca5a5' }}>{priorityCounts.hot} urgentes</span>}
                  </div>
                </div>
                <div className={`${panelStyle} p-3`} style={panelBg}>
                  <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(253,224,71,0.7)' }}>Articles 7j</p>
                  <div className="flex items-baseline gap-1.5">
                    <p className="text-2xl font-bold" style={{ color: '#fde68a' }}>{coverage?.total_articles_7d ?? 0}</p>
                    {trends && <TrendArrow pct={trends.articles_trend_pct} />}
                  </div>
                  <p className="text-[9px] mt-0.5" style={{ color: 'rgba(253,224,71,0.4)' }}>{coverage?.enriched_articles_7d ?? 0} enrichis IA</p>
                </div>
                <div className={`${panelStyle} p-3`} style={panelBg}>
                  <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(134,239,172,0.7)' }}>Climat</p>
                  {(() => {
                    const pos = sentimentDist['positif'] || sentimentDist['positive'] || 0
                    const neg = sentimentDist['négatif'] || sentimentDist['negatif'] || sentimentDist['negative'] || 0
                    const total = Object.values(sentimentDist).reduce((s, v) => s + v, 0)
                    const pctNeg = total > 0 ? Math.round(neg / total * 100) : 0
                    const isNeg = pctNeg > 30
                    return <>
                      <p className="text-lg font-bold" style={{ color: isNeg ? '#fca5a5' : '#86efac' }}>{isNeg ? 'Tendu' : 'Calme'}</p>
                      <div className="h-1.5 rounded-full overflow-hidden flex mt-1" style={{ background: 'rgba(255,255,255,0.08)' }}>
                        <div style={{ width: `${total > 0 ? Math.round(pos/total*100) : 33}%`, background: '#34d399' }} />
                        <div style={{ width: `${total > 0 ? Math.round((total-pos-neg)/total*100) : 34}%`, background: '#60a5fa' }} />
                        <div style={{ width: `${pctNeg}%`, background: '#f87171' }} />
                      </div>
                    </>
                  })()}
                </div>
                <div className={`${panelStyle} p-3`} style={panelBg}>
                  <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(167,139,250,0.7)' }}>Couverture</p>
                  <p className="text-2xl font-bold" style={{ color: '#c4b5fd' }}>{coverage?.affiliation_rate ?? 0}%</p>
                  <p className="text-[9px] mt-0.5" style={{ color: 'rgba(167,139,250,0.4)' }}>{coverage?.total_transcriptions_7d ?? 0} radios</p>
                </div>
              </div>
            )}

            {/* Alertes critiques */}
            {criticals.length > 0 && (
              <div className={`${panelStyle} p-3`} style={panelBg}>
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" style={{ boxShadow: '0 0 8px rgba(239,68,68,0.5)' }} />
                  <h2 className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: '#f87171' }}>Alertes</h2>
                </div>
                <div className="space-y-1">
                  {criticals.slice(0, 3).map((a) => (
                    <Link key={a._id} href={`/affairs/${a._id}`}>
                      <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg cursor-pointer transition-all hover:translate-x-0.5"
                        style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)' }}>
                        <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
                        <p className="text-[11px] font-medium text-white truncate flex-1">{a.title || a.primary_entity}</p>
                        <span className="text-[10px] font-bold flex-shrink-0" style={{ color: '#f87171' }}>{Math.round((a.bmg || 0) * 100)}</span>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Top Affaires */}
            {topAffairs.length > 0 && (
              <div className={`${panelStyle} p-3`} style={panelBg}>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>Affaires du moment</h2>
                  <Link href="/affairs" className="text-[9px]" style={{ color: '#60a5fa' }}>Tout voir →</Link>
                </div>
                <div className="space-y-1">
                  {topAffairs.slice(0, 8).map(affair => {
                    const g = affair.gravity_score || 0
                    const color = g >= 0.7 ? '#f87171' : g >= 0.5 ? '#fbbf24' : '#34d399'
                    return (
                      <Link key={affair._id} href={`/affairs/${affair._id}`}>
                        <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg transition-all hover:bg-white/5 cursor-pointer">
                          <div className="w-1 h-6 rounded-full flex-shrink-0" style={{ background: color }} />
                          <div className="flex-1 min-w-0">
                            <p className="text-[11px] font-medium text-white truncate">{affair.title || affair.primary_entity}</p>
                            <div className="flex items-center gap-1.5">
                              <ThemeBadge theme={affair.theme || 'general'} />
                              <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>{affair.item_count || 0} items</span>
                            </div>
                          </div>
                          <span className="text-[10px] font-bold flex-shrink-0" style={{ color }}>{Math.round((affair.bmg || 0) * 100)}</span>
                        </div>
                      </Link>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Sujets tendance */}
            <div className={`${panelStyle} p-3`} style={panelBg}>
              <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Sujets tendance</h2>
              <TrendingTopics themes={themes} />
            </div>

            {/* ── Radio / Captures ── */}
            <div className={`${panelStyle} p-3`} style={panelBg}>
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'rgba(139,92,246,0.6)' }}>
                  Radio · Captures
                </h2>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold"
                    style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}>
                    {radioToday.count} aujourd'hui
                  </span>
                  <button onClick={() => setRadioPanelOpen(!radioPanelOpen)}
                    className="text-[9px] text-white/30 hover:text-white/60">
                    {radioPanelOpen ? '▾' : '▸'}
                  </button>
                </div>
              </div>

              {/* Status indicators */}
              <div className="flex flex-wrap gap-1 mb-2">
                {radioHealth.slice(0, 6).map(stream => (
                  <div key={stream.key} className="flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-lg"
                    style={{ background: 'rgba(255,255,255,0.03)' }}
                    title={`${stream.name} — ${stream.status} (${stream.latency_ms}ms)`}>
                    <span className="w-1.5 h-1.5 rounded-full" style={{
                      background: stream.status === 'healthy' ? '#34d399' : stream.status === 'degraded' ? '#fbbf24' : '#f87171'
                    }} />
                    <span className="text-white/50 truncate max-w-[60px]">{stream.name?.split('_')[0] || stream.key}</span>
                  </div>
                ))}
              </div>

              {/* Expanded panel */}
              {radioPanelOpen && (
                <div className="space-y-1.5 mt-2 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  {/* Durée de capture */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[9px] text-white/30">Durée :</span>
                    {[30, 60, 120, 300, 600].map(d => (
                      <button key={d} onClick={() => setRadioCaptureDuration(d)}
                        className={`text-[9px] px-1.5 py-0.5 rounded-md transition-all ${radioCaptureDuration === d ? 'bg-violet-500/25 text-violet-300 font-semibold' : 'text-white/30 hover:text-white/50'}`}>
                        {d < 60 ? `${d}s` : `${d / 60}min`}
                      </button>
                    ))}
                  </div>
                  {radioHealth.map(stream => (
                    <div key={stream.key} className="flex items-center justify-between gap-2 py-1">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{
                          background: stream.status === 'healthy' ? '#34d399' : stream.status === 'degraded' ? '#fbbf24' : '#f87171'
                        }} />
                        <span className="text-[10px] text-white/70 truncate">{stream.name || stream.key}</span>
                        <span className="text-[8px] text-white/20">{stream.latency_ms}ms</span>
                      </div>
                      <button
                        onClick={() => handleRadioCapture(stream.key)}
                        disabled={radioCapturing !== null}
                        className="flex-shrink-0 text-[9px] px-2 py-0.5 rounded-lg font-semibold transition-all disabled:opacity-30"
                        style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.2)' }}>
                        {radioCapturing === stream.key ? `⟳ ${radioCaptureDuration}s...` : `▶ ${radioCaptureDuration < 60 ? radioCaptureDuration + 's' : radioCaptureDuration / 60 + 'min'}`}
                      </button>
                    </div>
                  ))}
                  <button onClick={loadRadioStatus}
                    className="w-full text-[9px] text-white/30 hover:text-white/50 mt-1 py-1">
                    ↻ Rafraîchir statuts
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* ══ RIGHT PANEL: Personnalités + Sentiment + Commune sélectionnée (desktop only) ══ */}
          <div className="pointer-events-auto absolute top-16 right-3 bottom-3 w-[280px] lg:w-[300px] hidden lg:flex flex-col gap-2.5 overflow-y-auto overflow-x-hidden scrollbar-hide" style={{ maxHeight: 'calc(100vh - 80px)' }}>

            {/* Commune sélectionnée */}
            {selectedCommune && mapBgData[selectedCommune] && (
              <div className={`${panelStyle} overflow-hidden`} style={{ ...panelBg, borderColor: 'rgba(220,38,38,0.3)' }}>
                {/* Header */}
                <div className="flex items-center justify-between p-3 border-b" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                  <h2 className="text-sm font-bold text-white">{selectedCommune}</h2>
                  <button onClick={() => setSelectedCommune(null)} className="text-[10px] px-1.5 py-0.5 rounded hover:bg-white/10 transition-colors" style={{ color: 'rgba(255,255,255,0.4)' }}>✕</button>
                </div>

                {/* Stats Grid */}
                <div className="p-3 border-b grid grid-cols-3 gap-2 text-center" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                  <div>
                    <p className="text-sm font-bold" style={{ color: '#60a5fa' }}>{(mapBgData[selectedCommune] as any)?.stats?.article_count || 0}</p>
                    <p className="text-[8px] uppercase" style={{ color: 'rgba(255,255,255,0.3)' }}>Articles</p>
                  </div>
                  <div>
                    <p className="text-sm font-bold" style={{ color: '#a78bfa' }}>{(mapBgData[selectedCommune] as any)?.stats?.transcription_count || 0}</p>
                    <p className="text-[8px] uppercase" style={{ color: 'rgba(255,255,255,0.3)' }}>Radios</p>
                  </div>
                  <div>
                    <p className="text-sm font-bold" style={{ color: '#fbbf24' }}>{(mapBgData[selectedCommune] as any)?.stats?.affair_count || 0}</p>
                    <p className="text-[8px] uppercase" style={{ color: 'rgba(255,255,255,0.3)' }}>Affaires</p>
                  </div>
                </div>

                {/* Affairs List */}
                {((mapBgData[selectedCommune] as any)?.affairs?.length || 0) > 0 && (
                  <div className="p-2">
                    <p className="text-[10px] font-semibold uppercase tracking-wider px-1 mb-2" style={{ color: 'rgba(255,255,255,0.4)' }}>Affaires principales</p>
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {((mapBgData[selectedCommune] as any)?.affairs || []).slice(0, 8).map((affair: any, idx: number) => {
                        const gravityColor = (affair.gravity_score || 0) >= 0.7 ? '#ef4444' : (affair.gravity_score || 0) >= 0.5 ? '#f97316' : (affair.gravity_score || 0) >= 0.3 ? '#eab308' : '#22c55e';
                        return (
                          <Link key={affair._id || idx} href={`/affairs/${affair._id}`}>
                            <div className="p-1.5 rounded-md hover:bg-white/10 transition-colors cursor-pointer group">
                              <div className="flex items-start gap-1.5 justify-between">
                                <div className="min-w-0 flex-1">
                                  <p className="text-[10px] font-medium text-white group-hover:text-indigo-300 transition-colors truncate">{affair.title || 'Sans titre'}</p>
                                  <p className="text-[8px]" style={{ color: 'rgba(255,255,255,0.4)' }}>{affair.theme || 'N/A'}</p>
                                </div>
                                <span className="text-[9px] font-bold flex-shrink-0 px-1.5 py-0.5 rounded" style={{ background: `${gravityColor}22`, color: gravityColor }}>
                                  {Math.round((affair.gravity_score || 0) * 100)}%
                                </span>
                              </div>
                            </div>
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Sentiment Gauge */}
            <div className={`${panelStyle} p-3`} style={panelBg}>
              <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Climat médiatique</h2>
              <SentimentGauge sentimentDist={sentimentDist} />
            </div>

            {/* Personnalités */}
            <div className={`${panelStyle} p-3`} style={panelBg}>
              <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Personnalités clés</h2>
              <TopPersonalities entities={entities} />
            </div>

            {/* Gravité */}
            {gravityDist && (
              <div className={`${panelStyle} p-3`} style={panelBg}>
                <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Gravité des affaires</h2>
                <GravityDonut distribution={gravityDist} />
              </div>
            )}

            {/* Sources */}
            {sources.length > 0 && (
              <div className={`${panelStyle} p-3`} style={panelBg}>
                <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Top sources</h2>
                <div className="space-y-1">
                  {sources.slice(0, 5).map((s, i) => (
                    <div key={s.name} className="flex items-center gap-2">
                      <span className="text-[9px] font-bold w-4 text-right" style={{ color: 'rgba(255,255,255,0.25)' }}>#{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[10px] text-white truncate">{s.name}</p>
                      </div>
                      <span className="text-[10px] font-semibold" style={{ color: '#60a5fa' }}>{s.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ══ BOTTOM BAR: Mini stats + Activité ══ */}
          <div className="pointer-events-auto absolute bottom-3 left-[340px] lg:left-[360px] right-[300px] lg:right-[320px] hidden lg:flex gap-2.5">
            {/* Activité mini chart */}
            {activity.length > 0 && (
              <div className={`${panelStyle} p-3 flex-1`} style={panelBg}>
                <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'rgba(255,255,255,0.35)' }}>Activité 7 jours</h2>
                <ActivityMiniChart data={activity} />
              </div>
            )}

            {/* Pipeline */}
            {stats && (
              <div className={`${panelStyle} p-3 flex-1`} style={panelBg}>
                <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'rgba(255,255,255,0.35)' }}>Pipeline</h2>
                <div className="flex items-center gap-2">
                  {[
                    { label: 'Candidats', value: stats.candidates_total, color: '#fbbf24' },
                    { label: 'Clusters', value: stats.clusters_active, color: '#facc15' },
                    { label: 'Actives', value: stats.affairs_active, color: '#60a5fa' },
                    { label: 'Veille', value: stats.affairs_stale, color: 'rgba(255,255,255,0.35)' },
                  ].map((s, i, arr) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <div className="text-center">
                        <p className="text-sm font-bold" style={{ color: s.color }}>{s.value ?? 0}</p>
                        <p className="text-[8px]" style={{ color: 'rgba(255,255,255,0.25)' }}>{s.label}</p>
                      </div>
                      {i < arr.length - 1 && <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.1)' }}>→</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Notifications ── */}
          <div className="pointer-events-auto fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
            {notifications.map(n => (
              <div key={n.id} className="animate-slide-up rounded-xl px-4 py-2.5 shadow-2xl text-xs font-medium flex items-center gap-2"
                style={{
                  background: n.type === 'hot' ? 'rgba(239,68,68,0.9)' : n.type === 'success' ? 'rgba(16,185,129,0.9)' : 'rgba(3,105,161,0.9)',
                  color: 'white',
                  backdropFilter: 'blur(12px)',
                  border: '1px solid rgba(255,255,255,0.15)',
                }}>
                <span>{n.type === 'hot' ? '🔴' : n.type === 'success' ? '✅' : 'ℹ️'}</span>
                <span>{n.text}</span>
                <button onClick={() => setNotifications(prev => prev.filter(x => x.id !== n.id))} className="ml-auto opacity-60 hover:opacity-100">✕</button>
              </div>
            ))}
          </div>


        {/* ══ SUMMARY MODAL ══ */}
        {summaryOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)' }}>
            <div className="relative w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl shadow-2xl"
              style={themeMode === 'light'
                ? { background: '#ffffff', border: '1px solid rgba(0,0,0,0.1)' }
                : { background: '#0f1219', border: '1px solid rgba(255,255,255,0.1)' }
              }>
              {/* Header */}
              <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b"
                style={themeMode === 'light'
                  ? { background: '#ffffff', borderColor: 'rgba(0,0,0,0.08)' }
                  : { background: '#0f1219', borderColor: 'rgba(255,255,255,0.08)' }
                }>
                <div>
                  <h2 className="text-lg font-bold" style={{ color: themeMode === 'light' ? '#1e293b' : '#f1f5f9' }}>
                    {summaryData?.summary?.titre || 'Résumé en cours...'}
                  </h2>
                  <div className="flex gap-2 mt-1">
                    <button onClick={() => handleGenerateSummary('journalier')}
                      className={`text-[10px] px-2.5 py-1 rounded-full font-semibold transition-all ${summaryPeriod === 'journalier' ? 'bg-indigo-500 text-white' : 'btn-glass'}`}>
                      Journalier
                    </button>
                    <button onClick={() => handleGenerateSummary('hebdomadaire')}
                      className={`text-[10px] px-2.5 py-1 rounded-full font-semibold transition-all ${summaryPeriod === 'hebdomadaire' ? 'bg-indigo-500 text-white' : 'btn-glass'}`}>
                      Hebdomadaire
                    </button>
                  </div>
                </div>
                <button onClick={() => setSummaryOpen(false)} className="text-xl opacity-50 hover:opacity-100 transition-opacity">✕</button>
              </div>

              {/* Body */}
              <div className="px-6 py-4">
                {summaryLoading ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-3">
                    <div className="text-3xl animate-spin">⟳</div>
                    <p className="text-sm opacity-50">Génération du résumé IA en cours...</p>
                    <p className="text-[10px] opacity-30">Analyse de {summaryPeriod === 'journalier' ? "24h" : "7 jours"} d'actualité</p>
                  </div>
                ) : summaryData?.summary ? (
                  <div className="space-y-6">
                    {/* Introduction */}
                    <p className="text-sm leading-relaxed opacity-80">{summaryData.summary.introduction}</p>

                    {/* Sections */}
                    {summaryData.summary.sections?.map((section, si) => (
                      <div key={si}>
                        <h3 className="text-sm font-bold mb-3 flex items-center gap-2" style={{ color: themeMode === 'light' ? '#075985' : '#7dd3fc' }}>
                          <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#0369A1' }} />
                          {section.titre}
                        </h3>
                        <div className="space-y-3 ml-3">
                          {section.articles?.map((art, ai) => (
                            <div key={ai} className="rounded-xl p-3 text-xs"
                              style={themeMode === 'light'
                                ? { background: 'rgba(0,0,0,0.03)', border: '1px solid rgba(0,0,0,0.06)' }
                                : { background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }
                              }>
                              <div className="flex items-start justify-between gap-2 mb-1">
                                <p className="font-semibold text-xs">{art.titre}</p>
                                <span className={`flex-shrink-0 text-[9px] px-1.5 py-0.5 rounded-full font-bold ${
                                  art.gravite === 'critique' ? 'badge-critical' :
                                  art.gravite === 'élevée' ? 'badge-high' :
                                  art.gravite === 'moyenne' ? 'badge-medium' : 'badge-low'
                                }`}>{art.gravite}</span>
                              </div>
                              <p className="opacity-70 leading-relaxed mb-1.5">{art.resume}</p>
                              {art.contexte && <p className="opacity-50 italic text-[10px] mb-1">{art.contexte}</p>}
                              <div className="flex flex-wrap gap-1.5 mt-1">
                                {art.communes?.map((c, ci) => (
                                  <span key={ci} className="text-[9px] px-1.5 py-0.5 rounded-full" style={themeMode === 'light' ? { background: 'rgba(3,105,161,0.1)', color: '#075985' } : { background: 'rgba(3,105,161,0.15)', color: '#7dd3fc' }}>{c}</span>
                                ))}
                                {art.sources?.map((s, si) => (
                                  <span key={si} className="text-[9px] px-1.5 py-0.5 rounded-full" style={themeMode === 'light' ? { background: 'rgba(245,158,11,0.1)', color: '#b45309' } : { background: 'rgba(245,158,11,0.15)', color: '#fbbf24' }}>{s}</span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}

                    {/* Tendances */}
                    {summaryData.summary.tendances && (
                      <div className="rounded-xl p-4" style={themeMode === 'light' ? { background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.15)' } : { background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)' }}>
                        <h3 className="text-xs font-bold mb-2" style={{ color: '#34d399' }}>Tendances</h3>
                        <p className="text-xs opacity-70 leading-relaxed">{summaryData.summary.tendances}</p>
                      </div>
                    )}

                    {/* À surveiller */}
                    {summaryData.summary.a_surveiller?.length > 0 && (
                      <div className="rounded-xl p-4" style={themeMode === 'light' ? { background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.15)' } : { background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}>
                        <h3 className="text-xs font-bold mb-2" style={{ color: '#fbbf24' }}>À surveiller</h3>
                        <ul className="space-y-1">
                          {summaryData.summary.a_surveiller.map((item, i) => (
                            <li key={i} className="text-xs opacity-70 flex items-start gap-1.5">
                              <span className="text-[10px] mt-0.5" style={{ color: '#fbbf24' }}>▸</span>
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Meta */}
                    <p className="text-[10px] opacity-30 text-right">
                      Généré le {new Date(summaryData.generated_at).toLocaleString('fr-FR')} · {summaryData.affairs_count} affaires · {summaryData.articles_count} articles
                    </p>
                  </div>
                ) : (
                  <p className="text-sm opacity-50 text-center py-8">Aucun résumé disponible</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── BOTTOM TIMELINE BAR ── */}
        {!loading && data?.daily_activity && data.daily_activity.length > 0 && (
          <div className="pointer-events-auto absolute bottom-3 left-3 right-3 lg:left-[360px]">
            <div className={`${panelStyle} px-4 py-2.5 flex items-end gap-[3px]`}
              style={themeMode === 'light'
                ? { background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }
                : panelBg
              }>
              <span className="text-[9px] font-semibold mr-2 self-center"
                style={{ color: themeMode === 'light' ? '#64748b' : 'rgba(255,255,255,0.4)' }}>
                30j
              </span>
              {(() => {
                const activity = data.daily_activity.slice(-30)
                const maxCount = Math.max(...activity.map((d: DailyActivity) => d.articles), 1)
                return activity.map((d: DailyActivity, i: number) => {
                  const height = Math.max(4, (d.articles / maxCount) * 32)
                  const isToday = i === activity.length - 1
                  return (
                    <div key={i} className="group relative flex-1 flex flex-col items-center">
                      <div className="absolute bottom-full mb-1 hidden group-hover:block z-50">
                        <div className="px-2 py-1 rounded-lg text-[9px] whitespace-nowrap font-medium"
                          style={themeMode === 'light'
                            ? { background: '#1e293b', color: '#f1f5f9' }
                            : { background: 'rgba(0,0,0,0.9)', color: '#f1f5f9' }
                          }>
                          {new Date(d.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })} — {d.articles} articles
                        </div>
                      </div>
                      <div
                        className="w-full rounded-sm transition-all duration-200 cursor-pointer hover:opacity-80"
                        style={{
                          height: `${height}px`,
                          minWidth: '3px',
                          background: isToday
                            ? '#DC2626'
                            : d.articles > maxCount * 0.7
                              ? (themeMode === 'light' ? '#f59e0b' : '#fbbf24')
                              : d.articles > maxCount * 0.3
                                ? (themeMode === 'light' ? '#0369A1' : '#0EA5E9')
                                : (themeMode === 'light' ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.15)'),
                          opacity: isToday ? 1 : 0.7,
                        }}
                      />
                    </div>
                  )
                })
              })()}
            </div>
          </div>
        )}
        </div>{/* fin pointer-events-none wrapper */}
      </div>{/* fin zone carte */}
    </div>
  )
}
