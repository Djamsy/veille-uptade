'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchCampaigns,
  createCampaign,
  fetchCampaignDetail,
  analyzeCampaign,
  compareCampaigns,
  Campaign,
  CampaignPost,
} from '../../lib/api'

// ── Couleurs plateformes ──
const PLAT_COLORS: Record<string, { icon: string; color: string }> = {
  instagram: { icon: '📸', color: '#e4405f' },
  facebook: { icon: '📘', color: '#1877f2' },
  linkedin: { icon: '💼', color: '#0a66c2' },
  twitter: { icon: '🐦', color: '#1da1f2' },
  youtube: { icon: '▶️', color: '#ff0000' },
}

const SENTIMENT_COLORS: Record<string, { icon: string; color: string; bg: string }> = {
  positif: { icon: '😊', color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
  négatif: { icon: '😠', color: '#ef4444', bg: 'rgba(239,68,68,0.15)' },
  neutre: { icon: '😐', color: '#94a3b8', bg: 'rgba(148,163,184,0.15)' },
  mitigé: { icon: '🤔', color: '#eab308', bg: 'rgba(234,179,8,0.15)' },
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function timeAgo(d: string): string {
  if (!d) return ''
  const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000)
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

// ── Post Card ──
function PostCard({ post, onHover }: { post: CampaignPost; onHover: (p: CampaignPost | null) => void }) {
  const s = post.stats || { views: 0, likes: 0, comments: 0, clicks: 0, reach: 0 }
  return (
    <div
      className="glass-card p-0 overflow-hidden cursor-pointer transition-all hover:scale-[1.02] hover:shadow-lg"
      onMouseEnter={() => onHover(post)}
      onMouseLeave={() => onHover(null)}
    >
      {/* Media preview */}
      <div className="relative h-40 bg-white/5 flex items-center justify-center overflow-hidden">
        {post.media_url ? (
          post.media_type === 'video' ? (
            <div className="text-4xl">🎬</div>
          ) : (
            <img src={post.media_url} alt="" className="w-full h-full object-cover" />
          )
        ) : (
          <div className="text-4xl opacity-30">📄</div>
        )}
        <span className="absolute top-2 right-2 px-2 py-0.5 rounded-full text-xs font-medium"
          style={{ background: 'rgba(0,0,0,0.6)', color: '#fff' }}>
          {post.media_type === 'video' ? '🎬 Vidéo' : post.media_type === 'carousel' ? '📸 Carrousel' : '📷 Photo'}
        </span>
      </div>
      {/* Content */}
      <div className="p-3">
        <h3 className="font-semibold text-sm mb-1 line-clamp-2" style={{ color: 'var(--text)' }}>
          {post.title || 'Sans titre'}
        </h3>
        <p className="text-xs opacity-60 mb-2">{timeAgo(post.published_at)}</p>
        <div className="flex gap-3 text-xs opacity-70">
          <span>👁 {formatNumber(s.views)}</span>
          <span>❤️ {formatNumber(s.likes)}</span>
          <span>💬 {s.comments}</span>
          <span>🔗 {s.clicks}</span>
        </div>
      </div>
    </div>
  )
}

// ── Stat Detail Tooltip ──
function StatTooltip({ post }: { post: CampaignPost }) {
  const ps = post.platform_stats || {}
  return (
    <div className="glass-card p-4 min-w-[280px]" style={{ background: 'var(--card-bg)' }}>
      <h4 className="font-semibold mb-3" style={{ color: 'var(--text)' }}>{post.title || 'Sans titre'}</h4>
      {Object.entries(ps).length > 0 ? (
        Object.entries(ps).map(([platform, stats]) => {
          const cfg = PLAT_COLORS[platform] || { icon: '🌐', color: '#888' }
          const st = stats as { views: number; likes: number; comments: number; clicks: number; reach: number }
          return (
            <div key={platform} className="mb-2 p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.05)' }}>
              <div className="flex items-center gap-2 mb-1">
                <span>{cfg.icon}</span>
                <span className="font-medium text-sm" style={{ color: cfg.color }}>
                  {platform.charAt(0).toUpperCase() + platform.slice(1)}
                </span>
              </div>
              <div className="grid grid-cols-5 gap-1 text-xs opacity-70">
                <span>👁 {formatNumber(st.views)}</span>
                <span>❤️ {formatNumber(st.likes)}</span>
                <span>💬 {st.comments}</span>
                <span>🔗 {st.clicks}</span>
                <span>📊 {formatNumber(st.reach)}</span>
              </div>
            </div>
          )
        })
      ) : (
        <p className="text-xs opacity-50">Stats par plateforme non encore disponibles</p>
      )}
    </div>
  )
}

// ── New Campaign Modal ──
function NewCampaignModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [keywords, setKeywords] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim()) return
    setLoading(true)
    try {
      await createCampaign({
        name: name.trim(),
        description: description.trim(),
        keywords: keywords.split(',').map(k => k.trim().toLowerCase()).filter(Boolean),
      })
      onCreated()
      onClose()
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={onClose}>
      <div className="glass-card p-6 w-full max-w-lg" onClick={e => e.stopPropagation()}
        style={{ background: 'var(--card-bg)' }}>
        <h2 className="text-xl font-bold mb-4" style={{ color: 'var(--text)' }}>Nouvelle campagne</h2>

        <label className="block text-sm mb-1 opacity-70">Nom de la campagne</label>
        <input className="input-dark w-full mb-3" placeholder="ex: Caribulles 2026"
          value={name} onChange={e => setName(e.target.value)} />

        <label className="block text-sm mb-1 opacity-70">Description</label>
        <textarea className="input-dark w-full mb-3 h-20 resize-none" placeholder="Objectif de la campagne..."
          value={description} onChange={e => setDescription(e.target.value)} />

        <label className="block text-sm mb-1 opacity-70">Mots-clés de détection (séparés par des virgules)</label>
        <input className="input-dark w-full mb-4" placeholder="caribulles, caribulle"
          value={keywords} onChange={e => setKeywords(e.target.value)} />

        <div className="flex gap-3 justify-end">
          <button className="btn-glass px-4 py-2" onClick={onClose}>Annuler</button>
          <button className="btn-glass px-4 py-2 font-semibold" onClick={handleSubmit} disabled={loading || !name.trim()}
            style={{ background: 'rgba(59,130,246,0.3)' }}>
            {loading ? '...' : 'Créer'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════
// PAGE PRINCIPALE
// ══════════════════════════════════════════════════════
export default function SocialPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [posts, setPosts] = useState<CampaignPost[]>([])
  const [hoveredPost, setHoveredPost] = useState<CampaignPost | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNewCampaign, setShowNewCampaign] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null)
  const [view, setView] = useState<'campagne' | 'analyse' | 'comparaison'>('campagne')
  const [compareA, setCompareA] = useState('')
  const [compareB, setCompareB] = useState('')
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null)
  const [comparingLoad, setComparingLoad] = useState(false)

  const loadCampaigns = useCallback(async () => {
    try {
      const data = await fetchCampaigns()
      setCampaigns(data.campaigns || [])
    } catch (e) { console.error(e) }
    setLoading(false)
  }, [])

  useEffect(() => { loadCampaigns() }, [loadCampaigns])

  const selectCampaign = async (campaign: Campaign) => {
    setSelectedCampaign(campaign)
    setAnalysis(campaign.ai_analysis || null)
    try {
      const data = await fetchCampaignDetail(campaign._id)
      setPosts(data.posts || [])
    } catch (e) { console.error(e) }
  }

  const runAnalysis = async () => {
    if (!selectedCampaign) return
    setAnalyzing(true)
    try {
      const data = await analyzeCampaign(selectedCampaign._id)
      if (data.ok) setAnalysis(data.analysis)
    } catch (e) { console.error(e) }
    setAnalyzing(false)
  }

  const runComparison = async () => {
    if (!compareA || !compareB) return
    setComparingLoad(true)
    try {
      const data = await compareCampaigns(compareA, compareB)
      if (data.ok) setComparison(data.comparison)
    } catch (e) { console.error(e) }
    setComparingLoad(false)
  }

  // Stats globales de la campagne sélectionnée
  const totalStats = selectedCampaign ? {
    views: selectedCampaign.total_views,
    likes: selectedCampaign.total_likes,
    comments: selectedCampaign.total_comments,
    clicks: selectedCampaign.total_clicks,
    reach: selectedCampaign.total_reach,
    posts: selectedCampaign.post_count,
  } : null

  const sentimentData = analysis?.sentiment as { global?: string; score?: number; themes?: string[]; positive_highlights?: string[]; negative_highlights?: string[] } | undefined
  const perfData = analysis?.performance as { best_format?: string; best_platform?: string; best_time?: string; best_day?: string; top_post?: string } | undefined
  const recommendations = (analysis?.recommendations || []) as string[]

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <main className="flex-1 p-6 ml-16 md:ml-56">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold" style={{ color: 'var(--text)' }}>Campagnes RS</h1>
            <p className="text-sm opacity-60">Conseil Départemental de Guadeloupe</p>
          </div>
          <button className="btn-glass px-4 py-2 font-medium" onClick={() => setShowNewCampaign(true)}
            style={{ background: 'rgba(59,130,246,0.2)' }}>
            + Nouvelle campagne
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          {(['campagne', 'analyse', 'comparaison'] as const).map(tab => (
            <button key={tab} className="btn-glass px-4 py-2 text-sm font-medium capitalize"
              style={{ background: view === tab ? 'rgba(59,130,246,0.25)' : 'transparent' }}
              onClick={() => setView(tab)}>
              {tab === 'campagne' ? '📋 Campagne' : tab === 'analyse' ? '📊 Analyse' : '⚖️ Comparaison'}
            </button>
          ))}
        </div>

        <div className="flex gap-6">
          {/* Sidebar campagnes */}
          <div className="w-64 shrink-0">
            <h3 className="text-sm font-semibold mb-3 opacity-70">Campagnes</h3>
            {loading ? (
              <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="skeleton h-12 rounded-lg" />)}</div>
            ) : campaigns.length === 0 ? (
              <p className="text-sm opacity-50">Aucune campagne. Créez-en une !</p>
            ) : (
              <div className="space-y-1">
                {campaigns.map(c => (
                  <button key={c._id} className="w-full text-left p-3 rounded-lg transition-all"
                    style={{
                      background: selectedCampaign?._id === c._id ? 'rgba(59,130,246,0.15)' : 'transparent',
                      color: 'var(--text)',
                    }}
                    onClick={() => selectCampaign(c)}>
                    <div className="font-medium text-sm">{c.name}</div>
                    <div className="text-xs opacity-50 mt-0.5">
                      {c.post_count} posts · {c.status === 'active' ? '🟢' : '⚪'} {c.status}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Contenu principal */}
          <div className="flex-1">
            {!selectedCampaign ? (
              <div className="glass-card p-12 text-center">
                <div className="text-5xl mb-4 opacity-30">📢</div>
                <p className="text-lg opacity-50">Sélectionnez une campagne</p>
              </div>
            ) : view === 'campagne' ? (
              <>
                {/* Stats globales */}
                {totalStats && (
                  <div className="grid grid-cols-6 gap-3 mb-6">
                    {[
                      { label: 'Posts', value: totalStats.posts, icon: '📝' },
                      { label: 'Vues', value: totalStats.views, icon: '👁' },
                      { label: 'Likes', value: totalStats.likes, icon: '❤️' },
                      { label: 'Commentaires', value: totalStats.comments, icon: '💬' },
                      { label: 'Clics', value: totalStats.clicks, icon: '🔗' },
                      { label: 'Reach', value: totalStats.reach, icon: '📊' },
                    ].map(s => (
                      <div key={s.label} className="glass-card p-3 text-center">
                        <div className="text-lg">{s.icon}</div>
                        <div className="text-xl font-bold" style={{ color: 'var(--text)' }}>
                          {formatNumber(s.value)}
                        </div>
                        <div className="text-xs opacity-50">{s.label}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Grille de posts */}
                <div className="relative">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {posts.map(post => (
                      <PostCard key={post._id} post={post} onHover={setHoveredPost} />
                    ))}
                  </div>
                  {posts.length === 0 && (
                    <div className="glass-card p-8 text-center">
                      <p className="opacity-50">Aucun post dans cette campagne.</p>
                      <p className="text-sm opacity-30 mt-1">Publiez depuis le bot Telegram pour commencer.</p>
                    </div>
                  )}

                  {/* Tooltip stats au survol */}
                  {hoveredPost && (
                    <div className="fixed right-8 top-1/3 z-40">
                      <StatTooltip post={hoveredPost} />
                    </div>
                  )}
                </div>
              </>
            ) : view === 'analyse' ? (
              <div>
                <div className="flex items-center gap-4 mb-6">
                  <h2 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>
                    Analyse : {selectedCampaign.name}
                  </h2>
                  <button className="btn-glass px-3 py-1.5 text-sm" onClick={runAnalysis} disabled={analyzing}
                    style={{ background: 'rgba(139,92,246,0.2)' }}>
                    {analyzing ? '🔄 Analyse en cours...' : '🧠 Lancer l\'analyse IA'}
                  </button>
                </div>

                {analysis ? (
                  <div className="space-y-4">
                    {/* Sentiment */}
                    {sentimentData && (
                      <div className="glass-card p-5">
                        <h3 className="font-semibold mb-3" style={{ color: 'var(--text)' }}>Sentiment</h3>
                        <div className="flex items-center gap-4 mb-3">
                          <span className="text-3xl">
                            {SENTIMENT_COLORS[sentimentData.global || 'neutre']?.icon || '😐'}
                          </span>
                          <div>
                            <div className="font-bold capitalize text-lg"
                              style={{ color: SENTIMENT_COLORS[sentimentData.global || 'neutre']?.color }}>
                              {sentimentData.global}
                            </div>
                            <div className="text-sm opacity-60">Score: {((sentimentData.score || 0) * 100).toFixed(0)}%</div>
                          </div>
                        </div>
                        {sentimentData.themes && sentimentData.themes.length > 0 && (
                          <div className="flex flex-wrap gap-2 mb-2">
                            {sentimentData.themes.map((t, i) => (
                              <span key={i} className="px-2 py-1 rounded-full text-xs"
                                style={{ background: 'rgba(59,130,246,0.15)', color: 'var(--text)' }}>{t}</span>
                            ))}
                          </div>
                        )}
                        {sentimentData.positive_highlights && (
                          <div className="mt-2">
                            <p className="text-xs font-medium opacity-70 mb-1">Points positifs</p>
                            {sentimentData.positive_highlights.map((h, i) => (
                              <p key={i} className="text-sm opacity-80 pl-3" style={{ color: '#22c55e' }}>+ {h}</p>
                            ))}
                          </div>
                        )}
                        {sentimentData.negative_highlights && (
                          <div className="mt-2">
                            <p className="text-xs font-medium opacity-70 mb-1">Points négatifs</p>
                            {sentimentData.negative_highlights.map((h, i) => (
                              <p key={i} className="text-sm opacity-80 pl-3" style={{ color: '#ef4444' }}>- {h}</p>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Performances */}
                    {perfData && (
                      <div className="glass-card p-5">
                        <h3 className="font-semibold mb-3" style={{ color: 'var(--text)' }}>Performances</h3>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          {[
                            { label: 'Meilleur format', value: perfData.best_format, icon: '🎨' },
                            { label: 'Meilleure plateforme', value: perfData.best_platform, icon: '🌐' },
                            { label: 'Meilleure heure', value: perfData.best_time, icon: '🕐' },
                            { label: 'Meilleur jour', value: perfData.best_day, icon: '📅' },
                          ].map(p => (
                            <div key={p.label} className="p-3 rounded-lg text-center"
                              style={{ background: 'rgba(255,255,255,0.05)' }}>
                              <div className="text-xl mb-1">{p.icon}</div>
                              <div className="font-semibold text-sm capitalize" style={{ color: 'var(--text)' }}>
                                {p.value || '—'}
                              </div>
                              <div className="text-xs opacity-50">{p.label}</div>
                            </div>
                          ))}
                        </div>
                        {perfData.top_post && (
                          <p className="mt-3 text-sm opacity-70">🏆 Top post : <b>{perfData.top_post}</b></p>
                        )}
                      </div>
                    )}

                    {/* Recommandations */}
                    {recommendations.length > 0 && (
                      <div className="glass-card p-5">
                        <h3 className="font-semibold mb-3" style={{ color: 'var(--text)' }}>Recommandations IA</h3>
                        <div className="space-y-2">
                          {recommendations.map((r, i) => (
                            <div key={i} className="flex gap-2 text-sm">
                              <span className="opacity-50">{i + 1}.</span>
                              <span style={{ color: 'var(--text)' }}>{r}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Résumé */}
                    {analysis.summary && (
                      <div className="glass-card p-5">
                        <h3 className="font-semibold mb-2" style={{ color: 'var(--text)' }}>Résumé</h3>
                        <p className="text-sm leading-relaxed" style={{ color: 'var(--text)', opacity: 0.8 }}>
                          {String(analysis.summary)}
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="glass-card p-8 text-center">
                    <div className="text-4xl mb-3 opacity-30">🧠</div>
                    <p className="opacity-50">Lancez l'analyse IA pour obtenir les insights</p>
                  </div>
                )}
              </div>
            ) : (
              /* Vue Comparaison */
              <div>
                <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text)' }}>Comparaison de campagnes</h2>
                <div className="flex gap-4 mb-6">
                  <select className="input-dark flex-1" value={compareA} onChange={e => setCompareA(e.target.value)}>
                    <option value="">Campagne A</option>
                    {campaigns.map(c => <option key={c._id} value={c._id}>{c.name}</option>)}
                  </select>
                  <span className="flex items-center text-xl opacity-30">⚡</span>
                  <select className="input-dark flex-1" value={compareB} onChange={e => setCompareB(e.target.value)}>
                    <option value="">Campagne B</option>
                    {campaigns.map(c => <option key={c._id} value={c._id}>{c.name}</option>)}
                  </select>
                  <button className="btn-glass px-4 py-2 text-sm" onClick={runComparison}
                    disabled={!compareA || !compareB || comparingLoad}
                    style={{ background: 'rgba(139,92,246,0.2)' }}>
                    {comparingLoad ? '...' : 'Comparer'}
                  </button>
                </div>

                {comparison ? (
                  <div className="glass-card p-5 space-y-4">
                    <p className="leading-relaxed" style={{ color: 'var(--text)' }}>
                      {String((comparison as any).comparison || '')}
                    </p>
                    {(comparison as any).improvements?.length > 0 && (
                      <div>
                        <h4 className="text-sm font-semibold opacity-70 mb-1">Progressions</h4>
                        {((comparison as any).improvements as string[]).map((t, i) => (
                          <p key={i} className="text-sm pl-3" style={{ color: '#22c55e' }}>+ {t}</p>
                        ))}
                      </div>
                    )}
                    {(comparison as any).regressions?.length > 0 && (
                      <div>
                        <h4 className="text-sm font-semibold opacity-70 mb-1">Régressions</h4>
                        {((comparison as any).regressions as string[]).map((t, i) => (
                          <p key={i} className="text-sm pl-3" style={{ color: '#ef4444' }}>- {t}</p>
                        ))}
                      </div>
                    )}
                    {(comparison as any).tips?.length > 0 && (
                      <div>
                        <h4 className="text-sm font-semibold opacity-70 mb-1">Conseils</h4>
                        {((comparison as any).tips as string[]).map((t, i) => (
                          <p key={i} className="text-sm pl-3 opacity-80">💡 {t}</p>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="glass-card p-8 text-center">
                    <div className="text-4xl mb-3 opacity-30">⚖️</div>
                    <p className="opacity-50">Sélectionnez deux campagnes et comparez</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {showNewCampaign && (
          <NewCampaignModal onClose={() => setShowNewCampaign(false)} onCreated={loadCampaigns} />
        )}
      </main>
    </div>
  )
}
