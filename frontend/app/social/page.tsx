'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchSocialStats,
  fetchSocialPosts,
  fetchSocialScrapeAll,
  fetchSocialConfig,
  SocialPost,
  SocialStats,
} from '../../lib/api'

const PLATFORM_CONFIG: Record<string, { icon: string; label: string; color: string; bg: string }> = {
  facebook: { icon: '📘', label: 'Facebook', color: '#1877f2', bg: 'rgba(24,119,242,0.1)' },
  instagram: { icon: '📸', label: 'Instagram', color: '#e4405f', bg: 'rgba(228,64,95,0.1)' },
  twitter: { icon: '🐦', label: 'Twitter / X', color: '#1da1f2', bg: 'rgba(29,161,242,0.1)' },
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return "a l'instant"
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

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      // Charger indépendamment pour ne pas tout casser si un appel échoue
      const [statsRes, postsRes, configRes] = await Promise.allSettled([
        fetchSocialStats(),
        fetchSocialPosts(activePlatform, 50),
        fetchSocialConfig(),
      ])

      if (statsRes.status === 'fulfilled') setStats(statsRes.value)
      if (postsRes.status === 'fulfilled') setPosts(postsRes.value.posts)
      if (configRes.status === 'fulfilled') setConfig(configRes.value)

      // Si tout a échoué, montrer l'erreur
      const allFailed = [statsRes, postsRes, configRes].every(r => r.status === 'rejected')
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

  const [scrapeResult, setScrapeResult] = useState<string | null>(null)

  const handleScrape = async () => {
    setScraping(true)
    setError(null)
    setScrapeResult(null)
    try {
      const result = await fetchSocialScrapeAll()
      const r = result as Record<string, unknown>
      const total = (r?.total_saved as number) || 0
      const enriched = (r?.enriched as number) || 0
      if (total > 0) {
        setScrapeResult(`${total} posts recuperes, ${enriched} enrichis par IA`)
      } else {
        setScrapeResult('0 posts recuperes — le plan Apify FREE peut limiter le scraping (proxy residentiel requis pour Facebook/Instagram)')
      }
      await loadData()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur scraping')
    } finally {
      setScraping(false)
    }
  }

  const apifyConfigured = config ? !!(config as Record<string, unknown>).apify_configured : null // null = unknown

  return (
    <div className="flex">
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-5 lg:p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">
                Reseaux Sociaux
              </h1>
              <p className="text-[11px] mt-0.5 font-medium" style={{ color: 'rgba(255,255,255,0.25)' }}>
                Veille Facebook, Instagram & Twitter/X via Apify
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={loadData}
                disabled={loading}
                className="btn-glass px-3 py-1.5 text-xs disabled:opacity-40"
              >
                <span className="flex items-center gap-1.5">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Rafraichir
                </span>
              </button>
              <button
                onClick={handleScrape}
                disabled={scraping || apifyConfigured === false}
                className="btn-primary px-4 py-1.5 text-xs disabled:opacity-40"
              >
                {scraping ? (
                  <span className="flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    Scraping...
                  </span>
                ) : 'Lancer scraping'}
              </button>
            </div>
          </div>

          {/* Warning APIFY_TOKEN */}
          {apifyConfigured === false && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-3"
              style={{ background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)', color: '#facc15' }}>
              <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <strong>APIFY_TOKEN non configure.</strong>{' '}
                <span style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Ajoutez la variable d&apos;environnement APIFY_TOKEN dans Render.
                </span>
              </div>
            </div>
          )}

          {/* Scrape result */}
          {scrapeResult && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-3" style={{
              background: scrapeResult.startsWith('0') ? 'rgba(234,179,8,0.08)' : 'rgba(22,163,74,0.08)',
              border: `1px solid ${scrapeResult.startsWith('0') ? 'rgba(234,179,8,0.2)' : 'rgba(22,163,74,0.2)'}`,
              color: scrapeResult.startsWith('0') ? '#facc15' : '#4ade80',
            }}>
              <span>{scrapeResult.startsWith('0') ? '⚠️' : '✅'}</span>
              {scrapeResult}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm" style={{
              background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.15)', color: '#f87171'
            }}>
              {error}
            </div>
          )}

          {/* Stats Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6 stagger-fade">
            {Object.entries(PLATFORM_CONFIG).map(([key, cfg]) => {
              const platStats = stats?.stats?.[key]
              const isSelected = activePlatform === key
              return (
                <button
                  key={key}
                  onClick={() => setActivePlatform(activePlatform === key ? undefined : key)}
                  className="glass-card-static p-5 text-left transition-all hover:scale-[1.01]"
                  style={{
                    borderColor: isSelected ? cfg.color : undefined,
                    boxShadow: isSelected ? `0 0 20px ${cfg.color}20` : undefined,
                  }}
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-2xl">{cfg.icon}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                      style={{
                        background: (platStats?.last_24h || 0) > 0 ? 'rgba(22,163,74,0.12)' : 'rgba(220,38,38,0.1)',
                        color: (platStats?.last_24h || 0) > 0 ? '#4ade80' : '#f87171',
                        border: `1px solid ${(platStats?.last_24h || 0) > 0 ? 'rgba(22,163,74,0.25)' : 'rgba(220,38,38,0.2)'}`,
                      }}>
                      {(platStats?.last_24h || 0) > 0 ? `${platStats?.last_24h} nouveaux` : 'Aucun'}
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-white mb-2">{cfg.label}</h3>
                  <div className="flex gap-4 text-[11px]" style={{ color: 'rgba(255,255,255,0.35)' }}>
                    <span>24h: <strong className="text-white/70">{platStats?.last_24h || 0}</strong></span>
                    <span>7j: <strong className="text-white/70">{platStats?.last_7d || 0}</strong></span>
                    <span>Total: <strong className="text-white/70">{platStats?.total || 0}</strong></span>
                  </div>
                  {platStats?.last_scraped && (
                    <p className="text-[10px] mt-2" style={{ color: 'rgba(255,255,255,0.18)' }}>
                      Dernier scrape : {timeAgo(platStats.last_scraped)}
                    </p>
                  )}
                </button>
              )
            })}
          </div>

          {/* Filter tabs */}
          <div className="flex gap-2 mb-5 flex-wrap">
            <button
              onClick={() => setActivePlatform(undefined)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
              style={{
                background: !activePlatform ? '#2563eb' : 'rgba(37,99,235,0.08)',
                color: !activePlatform ? '#fff' : 'rgba(255,255,255,0.4)',
                border: `1px solid ${!activePlatform ? '#2563eb' : 'rgba(37,99,235,0.15)'}`,
              }}
            >
              Tous
            </button>
            {Object.entries(PLATFORM_CONFIG).map(([key, cfg]) => (
              <button
                key={key}
                onClick={() => setActivePlatform(activePlatform === key ? undefined : key)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                style={{
                  background: activePlatform === key ? cfg.color : 'rgba(255,255,255,0.03)',
                  color: activePlatform === key ? '#fff' : 'rgba(255,255,255,0.4)',
                  border: `1px solid ${activePlatform === key ? cfg.color : 'rgba(255,255,255,0.06)'}`,
                }}
              >
                {cfg.icon} {cfg.label}
              </button>
            ))}
          </div>

          {/* Posts Feed */}
          <div className="space-y-3">
            {loading ? (
              <div className="glass-card-static p-12 text-center">
                <svg className="w-6 h-6 animate-spin mx-auto mb-3 text-blue-400" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                <p className="text-sm" style={{ color: 'rgba(255,255,255,0.3)' }}>Chargement...</p>
              </div>
            ) : posts.length === 0 ? (
              <div className="glass-card-static p-12 text-center">
                <div className="text-4xl mb-3">📱</div>
                <p className="text-sm font-medium text-white/50 mb-1">Aucun post recupere</p>
                <p className="text-xs" style={{ color: 'rgba(255,255,255,0.25)' }}>
                  {apifyConfigured !== false
                    ? 'Lancez un scraping pour recuperer les posts.'
                    : 'Configurez APIFY_TOKEN dans Render.'}
                </p>
              </div>
            ) : (
              posts.map((post) => {
                const cfg = PLATFORM_CONFIG[post.platform] || PLATFORM_CONFIG.twitter
                return (
                  <div key={post._id} className="glass-card p-4 cursor-default">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
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

                    <p className="text-[13px] leading-relaxed mb-3" style={{ color: 'rgba(255,255,255,0.6)' }}>
                      {post.text?.slice(0, 300)}{(post.text?.length || 0) > 300 ? '...' : ''}
                    </p>

                    {/* AI enrichment tags */}
                    {(post as Record<string, unknown>).ai_summary && (
                      <div className="mb-3 px-3 py-2 rounded-lg text-[11px]"
                        style={{ background: 'rgba(37,99,235,0.06)', border: '1px solid rgba(37,99,235,0.1)', color: 'rgba(255,255,255,0.5)' }}>
                        🧠 {String((post as Record<string, unknown>).ai_summary).slice(0, 200)}
                      </div>
                    )}

                    <div className="flex items-center gap-4 text-[11px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                      <span>❤️ {post.likes || 0}</span>
                      {post.comments !== undefined && <span>💬 {post.comments}</span>}
                      {post.shares !== undefined && <span>🔄 {post.shares}</span>}
                      {post.retweets !== undefined && <span>🔁 {post.retweets}</span>}
                      {post.url && (
                        <a href={post.url} target="_blank" rel="noopener noreferrer"
                          className="ml-auto text-blue-400 hover:text-blue-300 transition-colors font-medium">
                          Voir le post ↗
                        </a>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
