'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchSocialStats,
  fetchSocialPosts,
  fetchSocialScrapeAll,
  fetchSocialScrapeSingle,
  fetchSocialConfig,
  fetchSocialSentiment,
  fetchSocialPostDetail,
  SocialPost,
  SocialStats,
  SocialSentiment,
} from '../../lib/api'

/* ── Platform configs ───────────────────────────── */
const PLAT: Record<string, { icon: string; label: string; color: string; bg: string; glow: string }> = {
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

function gravityColor(g: number): string {
  if (g >= 0.7) return '#ef4444'
  if (g >= 0.4) return '#f59e0b'
  return '#22c55e'
}

function gravityLabel(g: number): string {
  if (g >= 0.7) return 'Critique'
  if (g >= 0.4) return 'Modérée'
  return 'Faible'
}

/* ══════════════════════════════════════════════════
   POST DETAIL MODAL
   ══════════════════════════════════════════════════ */
function PostModal({ post, onClose }: { post: SocialPost; onClose: () => void }) {
  const [detail, setDetail] = useState<(SocialPost & { raw?: Record<string, unknown> }) | null>(null)
  const [loading, setLoading] = useState(true)
  const cfg = PLAT[post.platform] || PLAT.twitter

  useEffect(() => {
    setLoading(true)
    fetchSocialPostDetail(post._id)
      .then(r => setDetail(r.post))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [post._id])

  const d = detail || post
  const gravity = d.gravity_score || 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-fade-in" />

      {/* Modal */}
      <div
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl animate-pop"
        style={{ background: 'rgba(10,16,30,0.97)', border: '1px solid rgba(255,255,255,0.08)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Top accent stripe */}
        <div className="h-1 rounded-t-2xl" style={{ background: `linear-gradient(90deg, ${cfg.color}, ${cfg.color}80, transparent)` }} />

        {/* Header */}
        <div className="flex items-center justify-between p-5 pb-3">
          <div className="flex items-center gap-3">
            <span className="text-[11px] px-2.5 py-1 rounded-full font-semibold"
              style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}40` }}>
              {cfg.icon} {cfg.label}
            </span>
            <span className="text-base font-bold text-white">@{d.author}</span>
          </div>
          <button onClick={onClose} className="text-white/30 hover:text-white/70 transition-colors text-xl leading-none p-1">✕</button>
        </div>

        {/* Image preview */}
        {d.image_url && (
          <div className="px-5 mb-3">
            <img
              src={d.image_url}
              alt="Publication"
              className="w-full max-h-80 object-cover rounded-xl"
              style={{ border: '1px solid rgba(255,255,255,0.06)' }}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          </div>
        )}

        {/* Full text */}
        <div className="px-5 mb-4">
          <p className="text-sm leading-relaxed" style={{ color: 'rgba(255,255,255,0.7)' }}>
            {d.text || 'Aucun texte disponible'}
          </p>
        </div>

        {/* Engagement stats */}
        <div className="mx-5 mb-4 grid grid-cols-4 gap-2">
          {[
            { label: 'Likes', value: d.likes || 0, icon: '❤️', color: '#ef4444' },
            { label: 'Commentaires', value: d.comments || 0, icon: '💬', color: '#3b82f6' },
            { label: d.platform === 'twitter' ? 'Retweets' : 'Partages', value: (d.retweets || d.shares || 0), icon: d.platform === 'twitter' ? '🔁' : '🔄', color: '#22c55e' },
            { label: 'Engagement total', value: (d.likes || 0) + (d.comments || 0) + (d.shares || 0) + (d.retweets || 0), icon: '📊', color: '#eab308' },
          ].map((s, i) => (
            <div key={i} className="text-center p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div className="text-lg mb-1">{s.icon}</div>
              <div className="text-lg font-bold text-white">{s.value.toLocaleString()}</div>
              <div className="text-[9px]" style={{ color: 'rgba(255,255,255,0.3)' }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* AI Analysis section */}
        {(d.ai_enriched || d.ai_summary || d.theme) && (
          <div className="mx-5 mb-4 p-4 rounded-xl" style={{ background: 'rgba(37,99,235,0.05)', border: '1px solid rgba(37,99,235,0.1)' }}>
            <h4 className="text-xs font-semibold text-blue-400 mb-3 flex items-center gap-2">
              🧠 Analyse IA
            </h4>

            {/* Gravity gauge */}
            {gravity > 0 && (
              <div className="flex items-center gap-3 mb-3">
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.4)' }}>Gravité</span>
                <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.05)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${gravity * 100}%`, background: gravityColor(gravity) }}
                  />
                </div>
                <span className="text-xs font-bold" style={{ color: gravityColor(gravity) }}>
                  {(gravity * 10).toFixed(1)}/10 — {gravityLabel(gravity)}
                </span>
              </div>
            )}

            {/* AI Summary */}
            {d.ai_summary && (
              <p className="text-[12px] leading-relaxed mb-3" style={{ color: 'rgba(255,255,255,0.55)' }}>
                {d.ai_summary}
              </p>
            )}

            {/* Tags */}
            <div className="flex flex-wrap gap-1.5">
              {d.theme && d.theme !== 'general' && (
                <span className="text-[9px] px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(234,179,8,0.1)', color: '#facc15', border: '1px solid rgba(234,179,8,0.2)' }}>
                  🏷️ {d.theme}
                </span>
              )}
              {d.elected?.map((el, i) => (
                <span key={i} className="text-[9px] px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(22,163,74,0.1)', color: '#4ade80', border: '1px solid rgba(22,163,74,0.2)' }}>
                  👤 {el}
                </span>
              ))}
              {d.institutions?.map((inst, i) => (
                <span key={i} className="text-[9px] px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(37,99,235,0.1)', color: '#60a5fa', border: '1px solid rgba(37,99,235,0.2)' }}>
                  🏛️ {inst}
                </span>
              ))}
              {d.keywords_found?.slice(0, 5).map((kw, i) => (
                <span key={i} className="text-[9px] px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(255,255,255,0.03)', color: 'rgba(255,255,255,0.35)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  {kw}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Meta */}
        <div className="px-5 pb-5 flex items-center justify-between text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>
          <div className="flex items-center gap-3">
            <span>Scrapé : {d.scraped_at ? timeAgo(d.scraped_at) : '?'}</span>
            {d.posted_at && <span>Publié : {new Date(d.posted_at).toLocaleDateString('fr-FR')}</span>}
            {d.ai_enriched && <span className="text-blue-400">✓ Enrichi IA</span>}
          </div>
          {d.url && (
            <a href={d.url} target="_blank" rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
              Voir l&apos;original ↗
            </a>
          )}
        </div>

        {loading && (
          <div className="absolute inset-0 flex items-center justify-center rounded-2xl" style={{ background: 'rgba(10,16,30,0.7)' }}>
            <div className="typing-dots"><span /><span /><span /></div>
          </div>
        )}
      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════
   MAIN PAGE
   ══════════════════════════════════════════════════ */
export default function SocialPage() {
  const [stats, setStats] = useState<SocialStats | null>(null)
  const [posts, setPosts] = useState<SocialPost[]>([])
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [sentiment, setSentiment] = useState<SocialSentiment | null>(null)
  const [activePlatform, setActivePlatform] = useState<string | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [scraping, setScraping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scrapeResult, setScrapeResult] = useState<{ msg: string; type: 'success' | 'warning' | 'error' } | null>(null)
  const [selectedPost, setSelectedPost] = useState<SocialPost | null>(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const results = await Promise.allSettled([
        fetchSocialStats(),
        fetchSocialPosts(activePlatform, 50),
        fetchSocialConfig(),
        fetchSocialSentiment(),
      ])

      if (results[0].status === 'fulfilled') setStats(results[0].value)
      if (results[1].status === 'fulfilled') setPosts(results[1].value?.posts || [])
      if (results[2].status === 'fulfilled') setConfig(results[2].value)
      if (results[3].status === 'fulfilled') setSentiment(results[3].value)

      if (results.every(r => r.status === 'rejected')) {
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
        setScrapeResult({ msg: `${total} posts sauvegardés, ${enriched} enrichis IA`, type: 'success' })
      } else if (fetched > 0) {
        setScrapeResult({ msg: `${fetched} posts récupérés — tous déjà en base`, type: 'warning' })
      } else {
        setScrapeResult({ msg: '0 posts — vérifiez plan Apify (proxy résidentiel requis)', type: 'warning' })
      }
      await loadData()
    } catch (e: unknown) {
      setScrapeResult({ msg: e instanceof Error ? e.message : 'Erreur scraping', type: 'error' })
    } finally {
      setScraping(false)
    }
  }

  const apifyConfigured = config ? !!(config as Record<string, unknown>).apify_configured : null

  const totalPosts = stats ? Object.values(stats.stats || {}).reduce((sum, p) => sum + (p?.total || 0), 0) : 0
  const total24h = stats ? Object.values(stats.stats || {}).reduce((sum, p) => sum + (p?.last_24h || 0), 0) : 0

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
              <button onClick={loadData} disabled={loading} className="btn-glass px-3 py-1.5 text-xs disabled:opacity-40">
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
                    Scraping...
                  </span>
                ) : '🚀 Lancer scraping'}
              </button>
            </div>
          </div>

          <div className="flag-stripe-animated mb-6" />

          {/* ── Alerts ──────────────────────────────── */}
          {apifyConfigured === false && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-3 animate-notif"
              style={{ background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)', color: '#facc15' }}>
              ⚠️ <strong>APIFY_TOKEN non configuré.</strong>
              <span style={{ color: 'rgba(255,255,255,0.4)' }}>Ajoutez la variable dans Render.</span>
            </div>
          )}
          {scrapeResult && (
            <div className={`mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-3 animate-notif`} style={{
              background: scrapeResult.type === 'success' ? 'rgba(22,163,74,0.08)' : scrapeResult.type === 'error' ? 'rgba(220,38,38,0.08)' : 'rgba(234,179,8,0.08)',
              border: `1px solid ${scrapeResult.type === 'success' ? 'rgba(22,163,74,0.2)' : scrapeResult.type === 'error' ? 'rgba(220,38,38,0.2)' : 'rgba(234,179,8,0.2)'}`,
              color: scrapeResult.type === 'success' ? '#4ade80' : scrapeResult.type === 'error' ? '#f87171' : '#facc15',
            }}>
              {scrapeResult.type === 'success' ? '✅' : scrapeResult.type === 'error' ? '❌' : '⚠️'} {scrapeResult.msg}
            </div>
          )}
          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm flex items-center gap-3 animate-notif" style={{
              background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.15)', color: '#f87171'
            }}>❌ {error}</div>
          )}

          {/* ══════════════════════════════════════════
              SENTIMENT GLOBAL (7j)
              ══════════════════════════════════════════ */}
          {sentiment && sentiment.global.total_posts > 0 && (
            <div className="mb-6 animate-fade-in">
              <h2 className="text-sm font-semibold text-white/60 mb-3 flex items-center gap-2">
                📊 Vue d&apos;ensemble (7 jours)
              </h2>

              {/* KPI row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 stagger-cards">
                {[
                  { label: 'Posts collectés', value: sentiment.global.total_posts, icon: '📝', color: '#60a5fa' },
                  { label: 'Engagement total', value: sentiment.global.total_engagement, icon: '🔥', color: '#f59e0b' },
                  { label: 'Commentaires', value: sentiment.global.total_comments, icon: '💬', color: '#22c55e' },
                  { label: 'Gravité moy.', value: `${(sentiment.global.avg_gravity * 10).toFixed(1)}/10`, icon: '⚡', color: gravityColor(sentiment.global.avg_gravity) },
                ].map((kpi, i) => (
                  <div key={i} className="glass-card-static p-4 text-center">
                    <div className="text-xl mb-1">{kpi.icon}</div>
                    <div className="text-xl font-bold animate-number-pop" style={{ color: kpi.color }}>
                      {typeof kpi.value === 'number' ? kpi.value.toLocaleString() : kpi.value}
                    </div>
                    <div className="text-[10px] mt-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>{kpi.label}</div>
                  </div>
                ))}
              </div>

              {/* Themes + Elected row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Top themes */}
                {sentiment.top_themes.length > 0 && (
                  <div className="glass-card-static p-4">
                    <h3 className="text-[11px] font-semibold text-white/40 mb-2">🏷️ Thèmes dominants</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {sentiment.top_themes.map((t, i) => (
                        <span key={i} className="text-[10px] px-2.5 py-1 rounded-full font-medium"
                          style={{ background: 'rgba(234,179,8,0.08)', color: '#facc15', border: '1px solid rgba(234,179,8,0.15)' }}>
                          {t.theme} <strong className="ml-0.5">({t.count})</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Top elected */}
                {sentiment.top_elected.length > 0 && (
                  <div className="glass-card-static p-4">
                    <h3 className="text-[11px] font-semibold text-white/40 mb-2">👤 Élus les plus mentionnés</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {sentiment.top_elected.map((el, i) => (
                        <span key={i} className="text-[10px] px-2.5 py-1 rounded-full font-medium"
                          style={{ background: 'rgba(22,163,74,0.08)', color: '#4ade80', border: '1px solid rgba(22,163,74,0.15)' }}>
                          {el.name} <strong className="ml-0.5">({el.count})</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Platform Stats Cards ───────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6 stagger-cards">
            {Object.entries(PLAT).map(([key, cfg]) => {
              const ps = stats?.stats?.[key]
              const isSelected = activePlatform === key
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
                      <span className="text-2xl">{cfg.icon}</span>
                      <h3 className="text-sm font-semibold text-white">{cfg.label}</h3>
                    </div>
                    {(ps?.last_24h || 0) > 0 && (
                      <span className="animate-number-pop text-[10px] px-2 py-0.5 rounded-full font-semibold"
                        style={{ background: 'rgba(22,163,74,0.12)', color: '#4ade80', border: '1px solid rgba(22,163,74,0.25)' }}>
                        +{ps?.last_24h}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2 mb-3">
                    {[
                      { v: ps?.last_24h || 0, l: '24h' },
                      { v: ps?.last_7d || 0, l: '7j' },
                      { v: ps?.total || 0, l: 'Total' },
                    ].map((s, i) => (
                      <div key={i} className="text-center px-2 py-1.5 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                        <div className="text-base font-bold text-white">{s.v}</div>
                        <div className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>{s.l}</div>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>
                      {ps?.last_scraped ? `Dernier: ${timeAgo(ps.last_scraped)}` : 'Jamais scrapé'}
                    </p>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleScrape(key) }}
                      disabled={scraping || apifyConfigured === false}
                      className="text-[10px] px-2 py-0.5 rounded-md font-medium transition-all hover:brightness-125 disabled:opacity-30"
                      style={{ background: `${cfg.color}20`, color: cfg.color, border: `1px solid ${cfg.color}30` }}
                    >Scraper</button>
                  </div>
                </button>
              )
            })}
          </div>

          {/* ── Filter tabs ────────────────────────── */}
          <div className="flex gap-2 mb-5 flex-wrap">
            <button
              onClick={() => setActivePlatform(undefined)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200"
              style={{
                background: !activePlatform ? '#2563eb' : 'rgba(37,99,235,0.06)',
                color: !activePlatform ? '#fff' : 'rgba(255,255,255,0.4)',
                border: `1px solid ${!activePlatform ? '#2563eb' : 'rgba(37,99,235,0.1)'}`,
                boxShadow: !activePlatform ? '0 2px 12px rgba(37,99,235,0.3)' : 'none',
              }}
            >Tous ({posts.length})</button>
            {Object.entries(PLAT).map(([key, cfg]) => (
              <button key={key}
                onClick={() => setActivePlatform(activePlatform === key ? undefined : key)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200"
                style={{
                  background: activePlatform === key ? cfg.color : 'rgba(255,255,255,0.03)',
                  color: activePlatform === key ? '#fff' : 'rgba(255,255,255,0.4)',
                  border: `1px solid ${activePlatform === key ? cfg.color : 'rgba(255,255,255,0.06)'}`,
                  boxShadow: activePlatform === key ? `0 2px 12px ${cfg.glow}` : 'none',
                }}
              >{cfg.icon} {cfg.label}</button>
            ))}
          </div>

          {/* ── Posts Feed ──────────────────────────── */}
          <div className="space-y-3 stagger-posts">
            {loading ? (
              [1, 2, 3].map(i => (
                <div key={i} className="glass-card-static p-5 animate-shimmer" style={{ animationDelay: `${i * 0.15}s` }}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-8 h-8 rounded-full skeleton" />
                    <div className="flex-1"><div className="h-3 w-32 skeleton mb-2 rounded" /><div className="h-2 w-20 skeleton rounded" /></div>
                  </div>
                  <div className="h-3 w-full skeleton mb-2 rounded" />
                  <div className="h-3 w-3/4 skeleton rounded" />
                </div>
              ))
            ) : posts.length === 0 ? (
              <div className="glass-card-static p-12 text-center animate-pop">
                <div className="text-5xl mb-4">📱</div>
                <p className="text-sm font-semibold text-white/60 mb-2">Aucun post récupéré</p>
                <p className="text-xs mb-5" style={{ color: 'rgba(255,255,255,0.25)' }}>
                  {apifyConfigured !== false ? 'Lancez un scraping pour commencer.' : 'Configurez APIFY_TOKEN dans Render.'}
                </p>
                {apifyConfigured !== false && (
                  <button onClick={() => handleScrape()} disabled={scraping} className="btn-primary px-5 py-2 text-sm">
                    {scraping ? 'Scraping...' : '🚀 Premier scraping'}
                  </button>
                )}
              </div>
            ) : (
              posts.map((post) => {
                const cfg = PLAT[post.platform] || PLAT.twitter
                const gravity = post.gravity_score || 0

                return (
                  <div
                    key={post._id}
                    className="glass-card p-0 overflow-hidden group cursor-pointer"
                    onClick={() => setSelectedPost(post)}
                  >
                    <div className="flex">
                      {/* Image preview — left side */}
                      {post.image_url && (
                        <div className="w-32 sm:w-40 flex-shrink-0 relative overflow-hidden">
                          <img
                            src={post.image_url}
                            alt=""
                            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                            style={{ minHeight: '120px' }}
                            onError={(e) => { (e.target as HTMLImageElement).parentElement!.style.display = 'none' }}
                          />
                          {post.media_type === 'video' && (
                            <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                              <span className="text-2xl">▶️</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Content — right side */}
                      <div className="flex-1 p-4 min-w-0">
                        {/* Header */}
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="flex items-center gap-2 flex-wrap min-w-0">
                            <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold flex-shrink-0"
                              style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}30` }}>
                              {cfg.icon} {cfg.label}
                            </span>
                            <span className="text-sm font-semibold text-white truncate">@{post.author}</span>
                            {gravity > 0 && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold flex-shrink-0"
                                style={{
                                  background: `${gravityColor(gravity)}15`,
                                  color: gravityColor(gravity),
                                  border: `1px solid ${gravityColor(gravity)}30`,
                                }}>
                                ⚡ {(gravity * 10).toFixed(1)}
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] flex-shrink-0" style={{ color: 'rgba(255,255,255,0.2)' }}>
                            {post.scraped_at ? timeAgo(post.scraped_at) : ''}
                          </span>
                        </div>

                        {/* Text preview */}
                        <p className="text-[12px] leading-relaxed mb-2 transition-colors group-hover:text-white/65 line-clamp-3"
                          style={{ color: 'rgba(255,255,255,0.5)' }}>
                          {post.text?.slice(0, 280)}{(post.text?.length || 0) > 280 ? '...' : ''}
                        </p>

                        {/* AI summary mini */}
                        {post.ai_summary && (
                          <div className="mb-2 text-[10px] px-2.5 py-1.5 rounded-lg truncate"
                            style={{ background: 'rgba(37,99,235,0.05)', border: '1px solid rgba(37,99,235,0.08)', color: 'rgba(255,255,255,0.4)' }}>
                            🧠 {post.ai_summary.slice(0, 120)}...
                          </div>
                        )}

                        {/* Tags row */}
                        {(post.theme || post.elected?.length) && (
                          <div className="flex flex-wrap gap-1 mb-2">
                            {post.theme && post.theme !== 'general' && (
                              <span className="text-[8px] px-1.5 py-0.5 rounded-full"
                                style={{ background: 'rgba(234,179,8,0.08)', color: '#facc15', border: '1px solid rgba(234,179,8,0.12)' }}>
                                {post.theme}
                              </span>
                            )}
                            {post.elected?.slice(0, 2).map((el, i) => (
                              <span key={i} className="text-[8px] px-1.5 py-0.5 rounded-full"
                                style={{ background: 'rgba(22,163,74,0.08)', color: '#4ade80', border: '1px solid rgba(22,163,74,0.12)' }}>
                                {el}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Engagement footer */}
                        <div className="flex items-center gap-3 text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                          {(post.likes || 0) > 0 && <span>❤️ {post.likes?.toLocaleString()}</span>}
                          {(post.comments || 0) > 0 && <span>💬 {post.comments?.toLocaleString()}</span>}
                          {(post.shares || 0) > 0 && <span>🔄 {post.shares?.toLocaleString()}</span>}
                          {(post.retweets || 0) > 0 && <span>🔁 {post.retweets?.toLocaleString()}</span>}
                          <span className="ml-auto text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity font-medium">
                            Voir détail →
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>

          <div className="h-8" />
        </div>
      </main>

      {/* ── Post Detail Modal ──────────────────── */}
      {selectedPost && <PostModal post={selectedPost} onClose={() => setSelectedPost(null)} />}
    </div>
  )
}
