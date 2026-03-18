'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchSocialStats,
  fetchSocialPosts,
  fetchSocialScrapeAll,
  fetchSocialScrapeSingle,
  fetchSocialConfig,
  SocialPost,
  SocialStats,
} from '../../lib/api'

const PLATFORM_CONFIG: Record<string, { icon: string; label: string; color: string; bg: string; glow: string }> = {
  facebook: { icon: '📘', label: 'Facebook', color: '#1877f2', bg: 'rgba(24,119,242,0.1)', glow: 'rgba(24,119,242,0.15)' },
  instagram: { icon: '📸', label: 'Instagram', color: '#e4405f', bg: 'rgba(228,64,95,0.1)', glow: 'rgba(228,64,95,0.15)' },
  twitter: { icon: '🐦', label: 'Twitter / X', color: '#1da1f2', bg: 'rgba(29,161,242,0.1)', glow: 'rgba(29,161,242,0.15)' },
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return "à l'instant"
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

export default function SocialPage() {
  const [stats, setStats] = useState<SocialStats | null>(null)
  const [posts, setPosts] = useState<SocialPost[]>([])
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [activePlatform, setActivePlatform] = useState<string | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [scraping, setScraping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scrapeResult, setScrapeResult] = useState<{ msg: string; type: 'success' | 'warning' | 'error' } | null>(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const results = await Promise.allSettled([
        fetchSocialStats(),
        fetchSocialPosts(activePlatform, 50),
        fetchSocialConfig(),
      ])

      if (results[0].status === 'fulfilled') setStats(results[0].value)
      else console.warn('Stats failed:', results[0].reason)

      if (results[1].status === 'fulfilled') {
        const data = results[1].value
        setPosts(data?.posts || [])
      } else {
        console.warn('Posts failed:', results[1].reason)
        setPosts([])
      }

      if (results[2].status === 'fulfilled') setConfig(results[2].value)
      else console.warn('Config failed:', results[2].reason)

      const allFailed = results.every(r => r.status === 'rejected')
      if (allFailed) {
        setError('Impossible de contacter le backend')
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }, [activePlatform])

  useEffect(() => { loadData() }, [loadData])

  const handleScrape = async (platform?: string) => {
    setScraping(true)
    setError(null)
    setScrapeResult(null)
    try {
      const result = platform
        ? await fetchSocialScrapeSingle(platform)
        : await fetchSocialScrapeAll()
      const r = result as Record<string, unknown>
      const total = (r?.total_saved as number) || (r?.saved as number) || 0
      const fetched = (r?.fetched as number) || (r?.total_saved as number) || 0
      const enriched = (r?.enriched as number) || 0

      if (total > 0) {
        setScrapeResult({
          msg: `${total} posts sauvegardés (${fetched} récupérés, ${enriched} enrichis IA)`,
          type: 'success'
        })
      } else if (fetched > 0) {
        setScrapeResult({
          msg: `${fetched} posts récupérés mais tous déjà en base`,
          type: 'warning'
        })
      } else {
        setScrapeResult({
          msg: '0 posts récupérés — vérifiez le plan Apify (proxy résidentiel requis pour FB/IG)',
          type: 'warning'
        })
      }
      await loadData()
    } catch (e: unknown) {
      setScrapeResult({
        msg: e instanceof Error ? e.message : 'Erreur scraping',
        type: 'error'
      })
    } finally {
      setScraping(false)
    }
  }

  const apifyConfigured = config ? !!(config as Record<string, unknown>).apify_configured : null

  const totalPosts = stats
    ? Object.values(stats.stats || {}).reduce((sum, p) => sum + (p?.total || 0), 0)
    : 0
  const total24h = stats
    ? Object.values(stats.stats || {}).reduce((sum, p) => sum + (p?.last_24h || 0), 0)
    : 0

  return (
    <div className="flex">
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-5 lg:p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-slide-up">

          {/* ── Header ─────────────────────────────── */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-2">
            <div className="animate-slide-left">
              <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight flex items-center gap-3">
                <span className="text-2xl">📡</span>
                Réseaux Sociaux
                {total24h > 0 && (
                  <span className="animate-number-pop text-xs px-2 py-0.5 rounded-full font-semibold"
                    style={{ background: 'rgba(22,163,74,0.12)', color: '#4ade80', border: '1px solid rgba(22,163,74,0.25)' }}>
                    +{total24h} / 24h
                  </span>
                )}
              </h1>
              <p className="text-[11px] mt-1 font-medium" style={{ color: 'rgba(255,255,255,0.25)' }}>
                Veille Facebook, Instagram & Twitter/X — {totalPosts} posts en base
              </p>
            </div>
            <div className="flex items-center gap-2 animate-slide-right">
              <button
                onClick={loadData}
                disabled={loading}
                className="btn-glass px-3 py-1.5 text-xs disabled:opacity-40"
              >
                <span className="flex items-center gap-1.5">
                  <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Rafraîchir
                </span>
              </button>
              <button
                onClick={() => handleScrape()}
                disabled={scraping || apifyConfigured === false}
                className={`btn-primary px-4 py-1.5 text-xs disabled:opacity-40 ${scraping ? 'scraping' : ''}`}
              >
                {scraping ? (
                  <span className="flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    Scraping en cours...
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Lancer scraping
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* ── Flag stripe ────────────────────────── */}
          <div className="flag-stripe-animated mb-6" />

          {/* ── Alerts zone ────────────────────────── */}
          {apifyConfigured === false && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-3 animate-notif"
              style={{ background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)', color: '#facc15' }}>
              <span className="text-lg">⚠️</span>
              <div>
                <strong>APIFY_TOKEN non configuré.</strong>{' '}
                <span style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Ajoutez la variable d&apos;environnement APIFY_TOKEN dans Render.
                </span>
              </div>
            </div>
          )}

          {scrapeResult && (
            <div className={`mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-3 animate-notif ${
              scrapeResult.type === 'success' ? 'animate-success-flash' : ''
            }`} style={{
              background: scrapeResult.type === 'success' ? 'rgba(22,163,74,0.08)'
                : scrapeResult.type === 'error' ? 'rgba(220,38,38,0.08)' : 'rgba(234,179,8,0.08)',
              border: `1px solid ${scrapeResult.type === 'success' ? 'rgba(22,163,74,0.2)'
                : scrapeResult.type === 'error' ? 'rgba(220,38,38,0.2)' : 'rgba(234,179,8,0.2)'}`,
              color: scrapeResult.type === 'success' ? '#4ade80'
                : scrapeResult.type === 'error' ? '#f87171' : '#facc15',
            }}>
              <span className="text-lg">{scrapeResult.type === 'success' ? '✅' : scrapeResult.type === 'error' ? '❌' : '⚠️'}</span>
              {scrapeResult.msg}
            </div>
          )}

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-3 animate-notif" style={{
              background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.15)', color: '#f87171'
            }}>
              <span className="text-lg">❌</span>
              {error}
            </div>
          )}

          {/* ── Platform Stats Cards ───────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6 stagger-cards">
            {Object.entries(PLATFORM_CONFIG).map(([key, cfg]) => {
              const platStats = stats?.stats?.[key]
              const isSelected = activePlatform === key
              const hasData = (platStats?.total || 0) > 0

              return (
                <button
                  key={key}
                  onClick={() => setActivePlatform(activePlatform === key ? undefined : key)}
                  className={`glass-card-static p-5 text-left transition-all duration-300 hover:scale-[1.02] group ${isSelected ? 'animate-border-glow' : ''}`}
                  style={{
                    borderColor: isSelected ? cfg.color : undefined,
                    boxShadow: isSelected ? `0 0 30px ${cfg.glow}` : undefined,
                  }}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2.5">
                      <span className="text-2xl group-hover:animate-float">{cfg.icon}</span>
                      <h3 className="text-sm font-semibold text-white">{cfg.label}</h3>
                    </div>
                    {hasData && (
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${(platStats?.last_24h || 0) > 0 ? 'animate-number-pop' : ''}`}
                        style={{
                          background: (platStats?.last_24h || 0) > 0 ? 'rgba(22,163,74,0.12)' : 'rgba(255,255,255,0.04)',
                          color: (platStats?.last_24h || 0) > 0 ? '#4ade80' : 'rgba(255,255,255,0.3)',
                          border: `1px solid ${(platStats?.last_24h || 0) > 0 ? 'rgba(22,163,74,0.25)' : 'rgba(255,255,255,0.06)'}`,
                        }}>
                        {(platStats?.last_24h || 0) > 0 ? `+${platStats?.last_24h} nouveau${(platStats?.last_24h || 0) > 1 ? 'x' : ''}` : 'Aucun récent'}
                      </span>
                    )}
                  </div>

                  {/* Stats row */}
                  <div className="grid grid-cols-3 gap-2 mb-3">
                    <div className="text-center px-2 py-1.5 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                      <div className="text-base font-bold text-white">{platStats?.last_24h || 0}</div>
                      <div className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>24h</div>
                    </div>
                    <div className="text-center px-2 py-1.5 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                      <div className="text-base font-bold text-white">{platStats?.last_7d || 0}</div>
                      <div className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>7 jours</div>
                    </div>
                    <div className="text-center px-2 py-1.5 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                      <div className="text-base font-bold text-white">{platStats?.total || 0}</div>
                      <div className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>Total</div>
                    </div>
                  </div>

                  {/* Last scraped + quick scrape */}
                  <div className="flex items-center justify-between">
                    {platStats?.last_scraped ? (
                      <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>
                        Dernier scrape : {timeAgo(platStats.last_scraped)}
                      </p>
                    ) : (
                      <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.15)' }}>Jamais scrapé</p>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); handleScrape(key) }}
                      disabled={scraping || apifyConfigured === false}
                      className="text-[10px] px-2 py-0.5 rounded-md font-medium transition-all hover:brightness-125 disabled:opacity-30"
                      style={{ background: `${cfg.color}20`, color: cfg.color, border: `1px solid ${cfg.color}30` }}
                    >
                      Scraper
                    </button>
                  </div>
                </button>
              )
            })}
          </div>

          {/* ── Filter tabs ────────────────────────── */}
          <div className="flex gap-2 mb-5 flex-wrap animate-fade-in">
            <button
              onClick={() => setActivePlatform(undefined)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200"
              style={{
                background: !activePlatform ? '#2563eb' : 'rgba(37,99,235,0.06)',
                color: !activePlatform ? '#fff' : 'rgba(255,255,255,0.4)',
                border: `1px solid ${!activePlatform ? '#2563eb' : 'rgba(37,99,235,0.1)'}`,
                boxShadow: !activePlatform ? '0 2px 12px rgba(37,99,235,0.3)' : 'none',
              }}
            >
              Tous ({posts.length})
            </button>
            {Object.entries(PLATFORM_CONFIG).map(([key, cfg]) => {
              const count = posts.filter(p => p.platform === key).length
              return (
                <button
                  key={key}
                  onClick={() => setActivePlatform(activePlatform === key ? undefined : key)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200"
                  style={{
                    background: activePlatform === key ? cfg.color : 'rgba(255,255,255,0.03)',
                    color: activePlatform === key ? '#fff' : 'rgba(255,255,255,0.4)',
                    border: `1px solid ${activePlatform === key ? cfg.color : 'rgba(255,255,255,0.06)'}`,
                    boxShadow: activePlatform === key ? `0 2px 12px ${cfg.glow}` : 'none',
                  }}
                >
                  {cfg.icon} {cfg.label} {count > 0 && `(${count})`}
                </button>
              )
            })}
          </div>

          {/* ── Posts Feed ──────────────────────────── */}
          <div className="space-y-3 stagger-posts">
            {loading ? (
              <>
                {[1, 2, 3].map(i => (
                  <div key={i} className="glass-card-static p-5 animate-shimmer" style={{ animationDelay: `${i * 0.15}s` }}>
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-8 h-8 rounded-full skeleton" />
                      <div className="flex-1">
                        <div className="h-3 w-32 skeleton mb-2 rounded" />
                        <div className="h-2 w-20 skeleton rounded" />
                      </div>
                    </div>
                    <div className="h-3 w-full skeleton mb-2 rounded" />
                    <div className="h-3 w-3/4 skeleton rounded" />
                  </div>
                ))}
              </>
            ) : posts.length === 0 ? (
              <div className="glass-card-static p-12 text-center animate-pop">
                <div className="text-5xl mb-4">📱</div>
                <p className="text-sm font-semibold text-white/60 mb-2">Aucun post récupéré</p>
                <p className="text-xs mb-5" style={{ color: 'rgba(255,255,255,0.25)' }}>
                  {apifyConfigured !== false
                    ? 'Cliquez sur "Lancer scraping" pour récupérer les derniers posts.'
                    : 'Configurez APIFY_TOKEN dans Render pour activer le scraping.'}
                </p>
                {apifyConfigured !== false && (
                  <button
                    onClick={() => handleScrape()}
                    disabled={scraping}
                    className="btn-primary px-5 py-2 text-sm"
                  >
                    {scraping ? 'Scraping...' : '🚀 Lancer le premier scraping'}
                  </button>
                )}
              </div>
            ) : (
              posts.map((post) => {
                const cfg = PLATFORM_CONFIG[post.platform] || PLATFORM_CONFIG.twitter
                const extPost = post as Record<string, unknown>

                return (
                  <div key={post._id} className="glass-card p-4 group">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-3 mb-2.5">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span className="text-[10px] px-2.5 py-0.5 rounded-full font-semibold transition-all duration-200 group-hover:scale-105"
                          style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}30` }}>
                          {cfg.icon} {cfg.label}
                        </span>
                        <span className="text-sm font-semibold text-white">
                          @{post.author}
                        </span>
                      </div>
                      <span className="text-[10px] flex-shrink-0" style={{ color: 'rgba(255,255,255,0.2)' }}>
                        {post.scraped_at ? timeAgo(post.scraped_at) : ''}
                      </span>
                    </div>

                    {/* Text */}
                    <p className="text-[13px] leading-relaxed mb-3 transition-colors duration-200 group-hover:text-white/70"
                      style={{ color: 'rgba(255,255,255,0.55)' }}>
                      {post.text?.slice(0, 400)}{(post.text?.length || 0) > 400 ? '...' : ''}
                    </p>

                    {/* AI enrichment */}
                    {extPost.ai_summary && (
                      <div className="mb-3 px-3 py-2 rounded-lg text-[11px] flex items-start gap-2 animate-fade-in"
                        style={{ background: 'rgba(37,99,235,0.06)', border: '1px solid rgba(37,99,235,0.1)', color: 'rgba(255,255,255,0.5)' }}>
                        <span className="text-sm mt-0.5">🧠</span>
                        <span>{String(extPost.ai_summary).slice(0, 200)}</span>
                      </div>
                    )}

                    {/* Tags */}
                    {(extPost.theme || (extPost.elected as string[])?.length) && (
                      <div className="flex flex-wrap gap-1.5 mb-3">
                        {extPost.theme && extPost.theme !== 'general' && (
                          <span className="text-[9px] px-2 py-0.5 rounded-full"
                            style={{ background: 'rgba(234,179,8,0.08)', color: '#facc15', border: '1px solid rgba(234,179,8,0.15)' }}>
                            {String(extPost.theme)}
                          </span>
                        )}
                        {(extPost.elected as string[])?.map((el: string, i: number) => (
                          <span key={i} className="text-[9px] px-2 py-0.5 rounded-full"
                            style={{ background: 'rgba(22,163,74,0.08)', color: '#4ade80', border: '1px solid rgba(22,163,74,0.15)' }}>
                            {el}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Footer: engagement + link */}
                    <div className="flex items-center gap-4 text-[11px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                      {(post.likes || 0) > 0 && <span className="transition-colors hover:text-red-400">❤️ {post.likes}</span>}
                      {(post.comments || 0) > 0 && <span className="transition-colors hover:text-blue-400">💬 {post.comments}</span>}
                      {(post.shares || 0) > 0 && <span className="transition-colors hover:text-green-400">🔄 {post.shares}</span>}
                      {(post.retweets || 0) > 0 && <span className="transition-colors hover:text-blue-400">🔁 {post.retweets}</span>}
                      {post.url && (
                        <a href={post.url} target="_blank" rel="noopener noreferrer"
                          className="ml-auto text-blue-400 hover:text-blue-300 transition-all duration-200 font-medium hover:underline">
                          Voir le post ↗
                        </a>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>

          {/* ── Bottom spacing ──────────────────────── */}
          <div className="h-8" />
        </div>
      </main>
    </div>
  )
}
