'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchCampaigns,
  createCampaign,
  fetchCampaignDetail,
  analyzeCampaign,
  compareCampaigns,
  publishPost,
  fetchPublicationStatus,
  fetchSocialStatsStatus,
  triggerGlobalScrape,
  scrapePostStats,
  Campaign,
  CampaignPost,
  ServiceStatus,
} from '../../lib/api'

// ── Couleurs plateformes ──
const PLAT_COLORS: Record<string, { icon: string; color: string; bg: string }> = {
  instagram: { icon: '📸', color: '#e4405f', bg: 'rgba(228,64,95,0.15)' },
  facebook: { icon: '📘', color: '#1877f2', bg: 'rgba(24,119,242,0.15)' },
  linkedin: { icon: '💼', color: '#0a66c2', bg: 'rgba(10,102,194,0.15)' },
  twitter: { icon: '🐦', color: '#1da1f2', bg: 'rgba(29,161,242,0.15)' },
  youtube: { icon: '▶️', color: '#ff0000', bg: 'rgba(255,0,0,0.15)' },
  tiktok: { icon: '🎵', color: '#fe2c55', bg: 'rgba(254,44,85,0.15)' },
}

const SENTIMENT_COLORS: Record<string, { icon: string; color: string; bg: string }> = {
  positif: { icon: '😊', color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
  négatif: { icon: '😠', color: '#ef4444', bg: 'rgba(239,68,68,0.15)' },
  neutre: { icon: '😐', color: '#94a3b8', bg: 'rgba(148,163,184,0.15)' },
  mitigé: { icon: '🤔', color: '#eab308', bg: 'rgba(234,179,8,0.15)' },
}

const DAY_NAMES = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const DAY_NAMES_FULL = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

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

function formatTime(d: string): string {
  if (!d) return ''
  const date = new Date(d)
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

function formatDateShort(d: Date): string {
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

// ── Week helpers ──
function getMonday(d: Date): Date {
  const date = new Date(d)
  const day = date.getDay()
  const diff = day === 0 ? -6 : 1 - day
  date.setDate(date.getDate() + diff)
  date.setHours(0, 0, 0, 0)
  return date
}

function getWeekDays(monday: Date): Date[] {
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday)
    d.setDate(d.getDate() + i)
    return d
  })
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
}

function getWeekLabel(monday: Date): string {
  const sunday = new Date(monday)
  sunday.setDate(sunday.getDate() + 6)
  const mStr = monday.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })
  const sStr = sunday.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
  return `${mStr} — ${sStr}`
}

// ══════════════════════════════════════════════════════
// CALENDAR POST ITEM (mini card in day column)
// ══════════════════════════════════════════════════════
function CalendarPostItem({
  post,
  onViewDetail,
  onScrape,
}: {
  post: CampaignPost
  onViewDetail: (p: CampaignPost) => void
  onScrape?: (id: string) => void
}) {
  const [hovered, setHovered] = useState(false)
  const [popupSide, setPopupSide] = useState<'right' | 'left'>('right')
  const ref = useRef<HTMLDivElement>(null)
  const s = post.stats || { views: 0, likes: 0, comments: 0, clicks: 0, reach: 0 }
  const platforms = Object.keys(post.platform_stats || {})
  const engagement = s.reach > 0 ? (((s.likes + s.comments + s.clicks) / s.reach) * 100).toFixed(1) : '0'
  const sentimentInfo = post.sentiment
    ? SENTIMENT_COLORS[post.sentiment.global] || SENTIMENT_COLORS['neutre']
    : null

  // Determine popup direction based on element position
  const handleMouseEnter = () => {
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect()
      const screenMid = window.innerWidth / 2
      setPopupSide(rect.left > screenMid ? 'left' : 'right')
    }
    setHovered(true)
  }

  return (
    <div
      ref={ref}
      className="relative group"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Mini card */}
      <div
        className="rounded-lg p-2 mb-1.5 cursor-pointer transition-all hover:scale-[1.03] hover:shadow-lg"
        style={{
          background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(255,255,255,0.08)',
        }}
        onClick={() => onViewDetail(post)}
      >
        {/* Time + platforms row */}
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] font-mono opacity-50">{formatTime(post.published_at)}</span>
          <div className="flex gap-0.5">
            {platforms.slice(0, 3).map(p => {
              const cfg = PLAT_COLORS[p.toLowerCase()] || { icon: '🌐', color: '#888', bg: '' }
              return (
                <span key={p} className="text-[10px]" style={{ color: cfg.color }} title={p}>
                  {cfg.icon}
                </span>
              )
            })}
            {platforms.length > 3 && (
              <span className="text-[9px] opacity-40">+{platforms.length - 3}</span>
            )}
          </div>
        </div>

        {/* Media thumbnail */}
        {post.media_url && (
          <div className="rounded overflow-hidden mb-1.5 h-16 relative">
            <img
              src={post.media_url}
              alt=""
              className="w-full h-full object-cover"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
            {post.media_type === 'video' && (
              <div className="absolute inset-0 bg-black/30 flex items-center justify-center">
                <span className="text-sm">▶️</span>
              </div>
            )}
          </div>
        )}

        {/* Title */}
        <p className="text-[11px] font-medium leading-tight line-clamp-2" style={{ color: 'var(--text)' }}>
          {post.title || (post.body || '').substring(0, 60) || 'Sans titre'}
        </p>

        {/* Quick stats row */}
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[10px] opacity-50">👁 {formatNumber(s.views)}</span>
          <span className="text-[10px] opacity-50">❤️ {formatNumber(s.likes)}</span>
          <span className="text-[10px] opacity-50">💬 {formatNumber(s.comments)}</span>
        </div>

        {/* Sentiment dot */}
        {sentimentInfo && (
          <div className="flex items-center gap-1 mt-1">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: sentimentInfo.color }} />
            <span className="text-[9px] capitalize opacity-50">{post.sentiment?.global}</span>
          </div>
        )}
      </div>

      {/* ── Hover Popup ── */}
      {hovered && (
        <div
          className="absolute z-50 w-72 rounded-xl p-4 shadow-2xl"
          style={{
            top: '0',
            [popupSide === 'right' ? 'left' : 'right']: 'calc(100% + 12px)',
            background: 'rgba(20,20,30,0.97)',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(255,255,255,0.12)',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start gap-3 mb-3">
            {post.media_url && (
              <div className="w-14 h-14 rounded-lg overflow-hidden flex-shrink-0">
                <img src={post.media_url} alt="" className="w-full h-full object-cover" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold line-clamp-2" style={{ color: 'var(--text)' }}>
                {post.title || 'Sans titre'}
              </p>
              <p className="text-[10px] opacity-50 mt-0.5">
                {post.campaign_name} · {timeAgo(post.published_at)}
              </p>
            </div>
          </div>

          {/* Platforms */}
          <div className="flex flex-wrap gap-1.5 mb-3">
            {platforms.map(p => {
              const cfg = PLAT_COLORS[p.toLowerCase()] || { icon: '🌐', color: '#888', bg: 'rgba(128,128,128,0.15)' }
              return (
                <span
                  key={p}
                  className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                  style={{ background: cfg.bg, color: cfg.color }}
                >
                  {cfg.icon} {p.charAt(0).toUpperCase() + p.slice(1)}
                </span>
              )
            })}
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-3 gap-2 mb-3">
            {[
              { label: 'Vues', value: s.views, icon: '👁', color: '#3b82f6' },
              { label: 'Likes', value: s.likes, icon: '❤️', color: '#ef4444' },
              { label: 'Commentaires', value: s.comments, icon: '💬', color: '#f59e0b' },
              { label: 'Clics', value: s.clicks, icon: '🔗', color: '#22c55e' },
              { label: 'Reach', value: s.reach, icon: '📊', color: '#06b6d4' },
              { label: 'Engagement', value: engagement, unit: '%', icon: '⚡', color: '#a78bfa' },
            ].map(stat => (
              <div key={stat.label} className="p-2 rounded-lg text-center" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <div className="text-xs mb-0.5">{stat.icon}</div>
                <div className="text-sm font-bold" style={{ color: stat.color }}>
                  {typeof stat.value === 'number' ? formatNumber(stat.value) : stat.value}{stat.unit || ''}
                </div>
                <div className="text-[9px] opacity-40">{stat.label}</div>
              </div>
            ))}
          </div>

          {/* Sentiment */}
          {sentimentInfo && post.sentiment && (
            <div
              className="flex items-center gap-2 p-2 rounded-lg mb-3"
              style={{ background: sentimentInfo.bg }}
            >
              <span className="text-lg">{sentimentInfo.icon}</span>
              <div>
                <span className="text-xs font-semibold capitalize" style={{ color: sentimentInfo.color }}>
                  {post.sentiment.global}
                </span>
                <span className="text-[10px] opacity-50 ml-2">
                  Score: {((post.sentiment.score || 0) * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          )}

          {/* Per-platform breakdown */}
          {Object.entries(post.platform_stats || {}).length > 0 && (
            <div className="space-y-1.5 mb-3">
              {Object.entries(post.platform_stats || {}).map(([platform, stats]) => {
                const cfg = PLAT_COLORS[platform.toLowerCase()] || { icon: '🌐', color: '#888', bg: '' }
                const st = stats as { views: number; likes: number; comments: number; clicks: number; reach: number }
                const eng = st.reach > 0 ? (((st.likes + st.comments + st.clicks) / st.reach) * 100).toFixed(1) : '0'
                return (
                  <div key={platform} className="flex items-center gap-2 text-[10px] p-1.5 rounded"
                    style={{ background: 'rgba(255,255,255,0.03)', borderLeft: `3px solid ${cfg.color}` }}>
                    <span>{cfg.icon}</span>
                    <span className="flex-1 opacity-60">
                      {formatNumber(st.views)} vues · {formatNumber(st.likes)} likes · {eng}%
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Comments preview */}
          {post.comments_scraped && post.comments_scraped.length > 0 && (
            <div className="mb-3">
              <p className="text-[10px] opacity-50 mb-1">💬 {post.comments_scraped.length} commentaires</p>
              <div className="space-y-1 max-h-16 overflow-y-auto">
                {(post.comments_scraped as any[]).slice(0, 2).map((c, i) => (
                  <p key={i} className="text-[10px] opacity-40 line-clamp-1">
                    {c.author && <b>{c.author}: </b>}{c.text}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Body preview */}
          {post.body && (
            <p className="text-[10px] opacity-40 line-clamp-2 mb-3 italic">
              {post.body.substring(0, 150)}
            </p>
          )}

          {/* Actions */}
          <div className="flex gap-2">
            <button
              className="flex-1 px-2 py-1.5 rounded-lg text-[11px] font-medium transition-all hover:scale-105"
              style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6', border: '1px solid rgba(59,130,246,0.2)' }}
              onClick={(e) => { e.stopPropagation(); if (onScrape && post._id) onScrape(post._id) }}
            >
              🔄 Scraper
            </button>
            <button
              className="flex-1 px-2 py-1.5 rounded-lg text-[11px] font-medium transition-all hover:scale-105"
              style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.2)' }}
              onClick={() => onViewDetail(post)}
            >
              👁 Détails
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════
// CALENDAR GRID
// ══════════════════════════════════════════════════════
function CalendarView({
  posts,
  campaigns,
  onViewDetail,
  onScrape,
}: {
  posts: CampaignPost[]
  campaigns: Campaign[]
  onViewDetail: (p: CampaignPost) => void
  onScrape?: (id: string) => void
}) {
  const [weekOffset, setWeekOffset] = useState(0)

  const monday = useMemo(() => {
    const m = getMonday(new Date())
    m.setDate(m.getDate() + weekOffset * 7)
    return m
  }, [weekOffset])

  const weekDays = useMemo(() => getWeekDays(monday), [monday])
  const today = new Date()

  // Group posts by day
  const postsByDay = useMemo(() => {
    const map: Record<number, CampaignPost[]> = {}
    for (let i = 0; i < 7; i++) map[i] = []
    posts.forEach(post => {
      const pd = new Date(post.published_at)
      weekDays.forEach((day, i) => {
        if (isSameDay(pd, day)) {
          map[i].push(post)
        }
      })
    })
    // Sort each day's posts by time
    Object.values(map).forEach(arr =>
      arr.sort((a, b) => new Date(a.published_at).getTime() - new Date(b.published_at).getTime())
    )
    return map
  }, [posts, weekDays])

  const totalThisWeek = Object.values(postsByDay).reduce((sum, arr) => sum + arr.length, 0)

  return (
    <div>
      {/* Week navigation */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <button
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-all hover:scale-105"
            style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
            onClick={() => setWeekOffset(o => o - 1)}
          >
            ← Sem. préc.
          </button>
          <button
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-all hover:scale-105"
            style={{
              background: weekOffset === 0 ? 'rgba(59,130,246,0.2)' : 'rgba(255,255,255,0.06)',
              color: weekOffset === 0 ? '#3b82f6' : 'var(--text)',
              border: `1px solid ${weekOffset === 0 ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.1)'}`,
            }}
            onClick={() => setWeekOffset(0)}
          >
            Aujourd'hui
          </button>
          <button
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-all hover:scale-105"
            style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
            onClick={() => setWeekOffset(o => o + 1)}
          >
            Sem. suiv. →
          </button>
        </div>

        <div className="text-right">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
            {getWeekLabel(monday)}
          </h3>
          <p className="text-xs opacity-50">
            {totalThisWeek} publication{totalThisWeek > 1 ? 's' : ''} cette semaine
          </p>
        </div>
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-px rounded-xl overflow-hidden" style={{
        background: 'rgba(255,255,255,0.06)',
        border: '1px solid rgba(255,255,255,0.08)',
      }}>
        {/* Day headers */}
        {weekDays.map((day, i) => {
          const isToday = isSameDay(day, today)
          return (
            <div
              key={i}
              className="p-3 text-center"
              style={{
                background: isToday ? 'rgba(59,130,246,0.1)' : 'rgba(255,255,255,0.02)',
                borderBottom: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <div className="text-xs font-semibold opacity-60">{DAY_NAMES[i]}</div>
              <div
                className="text-lg font-bold mt-0.5"
                style={{
                  color: isToday ? '#3b82f6' : 'var(--text)',
                }}
              >
                {day.getDate()}
              </div>
              <div className="text-[10px] opacity-40">{formatDateShort(day)}</div>
              {postsByDay[i].length > 0 && (
                <div className="mt-1">
                  <span className="inline-block px-1.5 py-0.5 rounded-full text-[9px] font-semibold"
                    style={{ background: 'rgba(59,130,246,0.2)', color: '#3b82f6' }}>
                    {postsByDay[i].length} post{postsByDay[i].length > 1 ? 's' : ''}
                  </span>
                </div>
              )}
            </div>
          )
        })}

        {/* Day columns with posts */}
        {weekDays.map((day, i) => {
          const isToday = isSameDay(day, today)
          const dayPosts = postsByDay[i]

          return (
            <div
              key={`col-${i}`}
              className="p-2"
              style={{
                background: isToday ? 'rgba(59,130,246,0.03)' : 'rgba(0,0,0,0.15)',
                minHeight: '280px',
              }}
            >
              {dayPosts.length === 0 ? (
                <div className="flex items-center justify-center h-full opacity-20">
                  <span className="text-2xl">·</span>
                </div>
              ) : (
                <div className="space-y-0">
                  {dayPosts.map(post => (
                    <CalendarPostItem
                      key={post._id}
                      post={post}
                      onViewDetail={onViewDetail}
                      onScrape={onScrape}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════
// CHANNEL SIDEBAR (like Buffer's left panel)
// ══════════════════════════════════════════════════════
function ChannelSidebar({
  posts,
  filterPlatform,
  setFilterPlatform,
}: {
  posts: CampaignPost[]
  filterPlatform: string
  setFilterPlatform: (p: string) => void
}) {
  // Collect unique platforms from all posts
  const platformCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    posts.forEach(p => {
      Object.keys(p.platform_stats || {}).forEach(plat => {
        const key = plat.toLowerCase()
        counts[key] = (counts[key] || 0) + 1
      })
    })
    return counts
  }, [posts])

  const totalPosts = posts.length

  return (
    <div className="w-full">
      {/* All channels */}
      <button
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 transition-all text-left"
        style={{
          background: !filterPlatform ? 'rgba(59,130,246,0.15)' : 'transparent',
          color: !filterPlatform ? '#3b82f6' : 'var(--text)',
        }}
        onClick={() => setFilterPlatform('')}
      >
        <span className="text-lg">📡</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium">Tous les canaux</div>
        </div>
        <span className="text-xs opacity-50 font-mono">{totalPosts}</span>
      </button>

      {/* Per platform */}
      {Object.entries(PLAT_COLORS).map(([platform, cfg]) => {
        const count = platformCounts[platform] || 0
        if (count === 0) return null
        const isActive = filterPlatform === platform
        return (
          <button
            key={platform}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 transition-all text-left"
            style={{
              background: isActive ? cfg.bg : 'transparent',
              color: isActive ? cfg.color : 'var(--text)',
            }}
            onClick={() => setFilterPlatform(isActive ? '' : platform)}
          >
            <span className="text-lg">{cfg.icon}</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium capitalize">{platform}</div>
            </div>
            <span className="text-xs opacity-50 font-mono">{count}</span>
          </button>
        )
      })}
    </div>
  )
}

// ── Post Detail Modal (kept from previous) ──
function PostDetailModal({
  post,
  onClose,
  onScrape
}: {
  post: CampaignPost
  onClose: () => void
  onScrape?: (postId: string) => void
}) {
  const [scraping, setScraping] = useState(false)
  const s = post.stats || { views: 0, likes: 0, comments: 0, clicks: 0, reach: 0 }
  const ps = post.platform_stats || {}

  const handleScrape = async () => {
    if (scraping || !post._id) return
    setScraping(true)
    try {
      if (onScrape) onScrape(post._id)
    } finally {
      setTimeout(() => setScraping(false), 3000)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={onClose}
    >
      <div
        className="glass-card w-full max-w-3xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--card-bg)' }}
      >
        <div className="sticky top-0 flex items-center justify-between p-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.08)', background: 'var(--card-bg)' }}>
          <h2 className="text-lg font-bold" style={{ color: 'var(--text)' }}>
            {post.title || 'Sans titre'}
          </h2>
          <button onClick={onClose} className="text-xl opacity-60 hover:opacity-100 transition-opacity">✕</button>
        </div>

        <div className="p-6 space-y-6">
          {post.media_url && (
            <div className="rounded-lg overflow-hidden" style={{ background: 'rgba(255,255,255,0.03)' }}>
              {post.media_type === 'video' ? (
                <div className="aspect-video bg-black flex items-center justify-center relative group">
                  <img src={post.media_url} alt="" className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-black/30 group-hover:bg-black/20 flex items-center justify-center transition-all">
                    <span className="text-5xl">▶️</span>
                  </div>
                </div>
              ) : (
                <img src={post.media_url} alt="" className="w-full" />
              )}
            </div>
          )}

          <div>
            <h3 className="text-sm font-semibold mb-2 opacity-70">Contenu du post</h3>
            <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text)', opacity: 0.9 }}>
              {post.body || 'Pas de contenu texte'}
            </p>
          </div>

          <div>
            <h3 className="text-sm font-semibold mb-3 opacity-70">Statistiques globales</h3>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
              {[
                { label: 'Vues', value: s.views, icon: '👁', color: 'var(--primary)' },
                { label: "J'aime", value: s.likes, icon: '❤️', color: '#ef4444' },
                { label: 'Commentaires', value: s.comments, icon: '💬', color: '#3b82f6' },
                { label: 'Clics', value: s.clicks, icon: '🔗', color: '#22c55e' },
                { label: 'Reach', value: s.reach, icon: '📊', color: '#f59e0b' },
                { label: 'Engagement', value: s.reach > 0 ? (((s.likes + s.comments + s.clicks) / s.reach) * 100).toFixed(1) : '0', unit: '%', icon: '⚡', color: '#a78bfa' },
              ].map(stat => (
                <div key={stat.label} className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.04)' }}>
                  <div className="text-xl mb-1">{stat.icon}</div>
                  <div className="text-lg font-bold" style={{ color: stat.color }}>
                    {formatNumber(typeof stat.value === 'number' ? stat.value : parseFloat(stat.value as string))}{(stat as any).unit || ''}
                  </div>
                  <div className="text-xs opacity-50">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>

          {Object.entries(ps).length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-3 opacity-70">Par plateforme</h3>
              <div className="space-y-3">
                {Object.entries(ps).map(([platform, stats]) => {
                  const cfg = PLAT_COLORS[platform.toLowerCase()] || { icon: '🌐', color: '#888', bg: '' }
                  const st = stats as { views: number; likes: number; comments: number; clicks: number; reach: number }
                  const eng = st.reach > 0 ? (((st.likes + st.comments + st.clicks) / st.reach) * 100).toFixed(1) : '0'
                  return (
                    <div key={platform} className="p-4 rounded-lg" style={{ background: 'rgba(255,255,255,0.04)', borderLeft: `4px solid ${cfg.color}` }}>
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-xl">{cfg.icon}</span>
                        <span className="font-semibold" style={{ color: cfg.color }}>
                          {platform.charAt(0).toUpperCase() + platform.slice(1)}
                        </span>
                      </div>
                      <div className="grid grid-cols-5 gap-2 text-sm">
                        <div>
                          <div className="text-lg font-bold opacity-70">{formatNumber(st.views)}</div>
                          <div className="text-xs opacity-50">Vues</div>
                        </div>
                        <div>
                          <div className="text-lg font-bold opacity-70">{formatNumber(st.likes)}</div>
                          <div className="text-xs opacity-50">J&apos;aime</div>
                        </div>
                        <div>
                          <div className="text-lg font-bold opacity-70">{formatNumber(st.comments)}</div>
                          <div className="text-xs opacity-50">Commentaires</div>
                        </div>
                        <div>
                          <div className="text-lg font-bold opacity-70">{formatNumber(st.reach)}</div>
                          <div className="text-xs opacity-50">Reach</div>
                        </div>
                        <div>
                          <div className="text-lg font-bold" style={{ color: '#a78bfa' }}>{eng}%</div>
                          <div className="text-xs opacity-50">Engagement</div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {post.comments_scraped && post.comments_scraped.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-3 opacity-70">Commentaires ({post.comments_scraped.length})</h3>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {(post.comments_scraped as any[]).map((comment, i) => (
                  <div key={i} className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.04)' }}>
                    {comment.author && <div className="font-semibold text-sm opacity-80 mb-1">{comment.author}</div>}
                    <p className="text-sm opacity-70">{comment.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-3 pt-4 border-t" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
            <button
              onClick={handleScrape}
              disabled={scraping}
              className="flex-1 px-4 py-2 rounded-lg font-medium transition-all hover:scale-105"
              style={{
                background: scraping ? 'rgba(234,179,8,0.2)' : 'rgba(59,130,246,0.15)',
                color: scraping ? '#eab308' : '#3b82f6',
                border: `1px solid ${scraping ? 'rgba(234,179,8,0.2)' : 'rgba(59,130,246,0.2)'}`,
              }}
            >
              {scraping ? '⏳ Scraping...' : '🔄 Scraper maintenant'}
            </button>
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 rounded-lg font-medium"
              style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.2)' }}
            >
              Fermer
            </button>
          </div>
        </div>
      </div>
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
      <div className="glass-card p-6 w-full max-w-lg" onClick={e => e.stopPropagation()} style={{ background: 'var(--card-bg)' }}>
        <h2 className="text-xl font-bold mb-4" style={{ color: 'var(--text)' }}>Nouvelle campagne</h2>
        <label className="block text-sm mb-1 opacity-70">Nom de la campagne</label>
        <input className="input-dark w-full mb-3" placeholder="ex: Caribulles 2026" value={name} onChange={e => setName(e.target.value)} />
        <label className="block text-sm mb-1 opacity-70">Description</label>
        <textarea className="input-dark w-full mb-3 h-20 resize-none" placeholder="Objectif de la campagne..." value={description} onChange={e => setDescription(e.target.value)} />
        <label className="block text-sm mb-1 opacity-70">Mots-clés de détection (séparés par des virgules)</label>
        <input className="input-dark w-full mb-4" placeholder="caribulles, caribulle" value={keywords} onChange={e => setKeywords(e.target.value)} />
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

// ── Publish Progress ──
const PUBLISH_STEPS = [
  { key: 'upload', label: 'Upload du média', icon: '📤' },
  { key: 'detect', label: 'Détection campagne', icon: '🔍' },
  { key: 'buffer', label: 'Publication Buffer', icon: '🌐' },
  { key: 'save', label: 'Sauvegarde', icon: '💾' },
]

function PublishProgress({ step, error }: { step: number; error: boolean }) {
  return (
    <div className="my-4">
      <div className="flex items-center gap-1 mb-2">
        {PUBLISH_STEPS.map((s, i) => (
          <div key={s.key} className="flex items-center flex-1">
            <div className="flex flex-col items-center flex-1">
              <div className="text-lg mb-1" style={{
                opacity: i <= step ? 1 : 0.3,
                filter: error && i === step ? 'grayscale(0)' : undefined,
              }}>
                {error && i === step ? '❌' : i < step ? '✅' : i === step ? s.icon : '⏳'}
              </div>
              <span className="text-[10px] text-center opacity-60">{s.label}</span>
            </div>
            {i < PUBLISH_STEPS.length - 1 && (
              <div className="h-0.5 w-full mx-1 rounded" style={{
                background: i < step ? '#22c55e' : 'rgba(255,255,255,0.1)',
                minWidth: '20px',
              }} />
            )}
          </div>
        ))}
      </div>
      <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
        <div className="h-full rounded-full transition-all duration-700" style={{
          width: error ? '100%' : `${((step + 1) / PUBLISH_STEPS.length) * 100}%`,
          background: error ? '#ef4444' : 'linear-gradient(90deg, #3b82f6, #22c55e)',
          animation: !error && step < PUBLISH_STEPS.length ? 'pulse 1.5s ease-in-out infinite' : undefined,
        }} />
      </div>
    </div>
  )
}

// ── Compress image client-side ──
async function compressImage(file: File, maxWidth = 1920, quality = 0.75): Promise<File> {
  if (!file.type.startsWith('image/')) return file
  if (file.size < 500_000) return file
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      let { width, height } = img
      if (width > maxWidth) {
        height = Math.round(height * (maxWidth / width))
        width = maxWidth
      }
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0, width, height)
      canvas.toBlob((blob) => {
        if (blob && blob.size < file.size) {
          resolve(new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' }))
        } else { resolve(file) }
      }, 'image/jpeg', quality)
    }
    img.onerror = () => resolve(file)
    img.src = URL.createObjectURL(file)
  })
}

// ── New Post Modal ──
function NewPostModal({ campaigns, selectedCampaignId, onClose, onPublished }: {
  campaigns: Campaign[]
  selectedCampaignId?: string
  onClose: () => void
  onPublished: () => void
}) {
  const [text, setText] = useState('')
  const [campaignId, setCampaignId] = useState(selectedCampaignId || '')
  const [media, setMedia] = useState<File | null>(null)
  const [mediaPreview, setMediaPreview] = useState('')
  const [loading, setLoading] = useState(false)
  const [publishStep, setPublishStep] = useState(-1)
  const [result, setResult] = useState<{ ok: boolean; campaign?: string; platforms?: number; error?: string; detail?: string } | null>(null)

  const handleMedia = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setMedia(file)
    if (file.type.startsWith('image/')) setMediaPreview(URL.createObjectURL(file))
    else setMediaPreview('')
  }

  const handleSubmit = async () => {
    if (!text.trim()) return
    setLoading(true)
    setResult(null)
    setPublishStep(0)
    try {
      const compressedMedia = media ? await compressImage(media) : undefined
      const res = await publishPost({
        text: text.trim(),
        campaign_id: campaignId || undefined,
        media: compressedMedia || undefined,
      })
      setPublishStep(3)
      setResult(res)
      if (res.ok) setTimeout(() => { onPublished(); onClose() }, 2500)
    } catch (e) {
      setResult({ ok: false, error: 'network', detail: (e as Error)?.message || 'Erreur réseau' })
      console.error(e)
    }
    setLoading(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={loading ? undefined : onClose}>
      <div className="glass-card w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}
        style={{ background: 'var(--card-bg)' }}>
        <div className="sticky top-0 flex items-center justify-between p-6 border-b" style={{ borderColor: 'rgba(255,255,255,0.08)', background: 'var(--card-bg)' }}>
          <h2 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Nouveau post</h2>
          <button onClick={onClose} disabled={loading} className="text-xl opacity-60 hover:opacity-100 transition-opacity">✕</button>
        </div>

        <div className="p-6 space-y-5">
          <div>
            <label className="block text-sm font-semibold mb-2" style={{ color: 'var(--text)' }}>Campagne</label>
            <select className="input-dark w-full" value={campaignId} onChange={e => setCampaignId(e.target.value)} disabled={loading}>
              <option value="">Détection automatique</option>
              {campaigns.map(c => <option key={c._id} value={c._id}>{c.name}</option>)}
            </select>
            <p className="text-xs opacity-50 mt-1">Laisser vide pour détection automatique</p>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Contenu du post</label>
              <span className="text-xs opacity-50">{text.length} caractères</span>
            </div>
            <textarea
              className="input-dark w-full resize-none focus:ring-2 focus:ring-blue-500"
              style={{ minHeight: '220px', borderRadius: '8px' }}
              placeholder="Écrivez votre contenu ici..."
              value={text} onChange={e => setText(e.target.value)} disabled={loading}
            />
          </div>

          <div>
            <label className="block text-sm font-semibold mb-2" style={{ color: 'var(--text)' }}>Média (optionnel)</label>
            <div className="mb-4">
              <label className={`inline-block px-4 py-3 rounded-lg text-sm font-medium transition-all ${loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:scale-105'}`}
                style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6', border: '1px dashed rgba(59,130,246,0.3)' }}>
                {media ? `📎 ${media.name}` : '📁 Cliquez pour sélectionner ou glissez'}
                <input type="file" accept="image/*,video/*" className="hidden" onChange={handleMedia} disabled={loading} />
              </label>
              {media && !loading && (
                <button className="ml-3 text-xs opacity-50 hover:opacity-80 transition-opacity"
                  onClick={() => { setMedia(null); setMediaPreview('') }}>✕ Supprimer</button>
              )}
            </div>
            {mediaPreview && (
              <div className="rounded-lg overflow-hidden mb-4" style={{ maxHeight: '280px' }}>
                <img src={mediaPreview} alt="preview" className="w-full h-full object-cover" />
              </div>
            )}
          </div>

          {loading && <PublishProgress step={publishStep} error={false} />}

          {result && (
            <div className="p-4 rounded-lg text-sm" style={{
              background: result.ok ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
              color: result.ok ? '#22c55e' : '#ef4444',
              border: `1px solid ${result.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
            }}>
              {result.ok ? (
                <div>
                  <div className="font-semibold mb-1">✅ Publication réussie !</div>
                  <div className="opacity-80">{result.platforms} plateforme(s) · Campagne : {result.campaign}</div>
                </div>
              ) : (
                <div>
                  <div className="font-semibold mb-1">❌ Publication échouée</div>
                  <div className="opacity-80">
                    {result.error === 'cloudinary_failed' && 'Cloudinary : upload média échoué. Vérifiez les clés CLOUDINARY_* sur Render.'}
                    {result.error === 'network' && `Erreur réseau : ${result.detail}`}
                    {result.error === 'server_error' && `Erreur serveur : ${result.detail}`}
                    {result.error && !['cloudinary_failed', 'network', 'server_error'].includes(result.error) && (<>Buffer : {result.detail || result.error}</>)}
                    {!result.error && 'Erreur inconnue. Consultez les logs Render.'}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex gap-3 p-6 border-t" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
          <button className="flex-1 px-4 py-2 rounded-lg font-medium" onClick={onClose} disabled={loading}
            style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.2)' }}>
            Annuler
          </button>
          <button className="flex-1 px-6 py-2 rounded-lg font-semibold transition-all" onClick={handleSubmit}
            disabled={loading || !text.trim()}
            style={{
              background: loading || !text.trim() ? 'rgba(100,100,100,0.2)' : 'rgba(34,197,94,0.3)',
              color: loading || !text.trim() ? 'rgba(255,255,255,0.4)' : '#22c55e',
              border: `1px solid ${loading || !text.trim() ? 'rgba(100,100,100,0.1)' : 'rgba(34,197,94,0.2)'}`,
            }}>
            {loading ? '⏳ Publication en cours...' : '🚀 Publier'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Status Panel ──
function StatusPanel({ status, statsStatus, onGlobalScrape }: {
  status: ServiceStatus | null
  statsStatus: { configured: boolean; platforms: string[] } | null
  onGlobalScrape?: () => void
}) {
  const [scraping, setScraping] = useState(false)
  if (!status) return null
  const services = [
    { label: 'Buffer', ok: status.buffer_configured, desc: 'Publication multi-plateforme' },
    { label: 'Cloudinary', ok: status.cloudinary_configured, desc: 'Hébergement média' },
    { label: 'Bot Telegram', ok: status.bot_configured, desc: 'Publication via Telegram' },
    { label: 'IA (Mistral)', ok: status.mistral_configured, desc: 'Analyse des campagnes' },
    { label: 'Apify Stats', ok: statsStatus?.configured || false, desc: statsStatus?.configured ? `Scraping: ${statsStatus?.platforms?.join(', ')}` : 'Scraping stats RS' },
  ]
  const allOk = services.every(s => s.ok)
  const someOk = services.some(s => s.ok)

  return (
    <div className="glass-card p-3 mb-4" style={{
      border: `1px solid ${allOk ? 'rgba(34,197,94,0.2)' : someOk ? 'rgba(234,179,8,0.2)' : 'rgba(239,68,68,0.2)'}`,
    }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm">{allOk ? '🟢' : someOk ? '🟡' : '🔴'}</span>
          <span className="text-xs font-medium opacity-70">
            {allOk ? 'Tous les services connectés' : someOk ? 'Configuration partielle' : 'Services non configurés'}
          </span>
        </div>
        {statsStatus?.configured && (
          <button
            onClick={async () => {
              setScraping(true)
              try { if (onGlobalScrape) onGlobalScrape() }
              finally { setTimeout(() => setScraping(false), 30000) }
            }}
            disabled={scraping}
            className="px-3 py-1 rounded-lg text-xs font-medium transition-all hover:scale-105"
            style={{
              background: scraping ? 'rgba(234,179,8,0.2)' : 'rgba(59,130,246,0.15)',
              color: scraping ? '#eab308' : '#3b82f6',
              border: `1px solid ${scraping ? 'rgba(234,179,8,0.3)' : 'rgba(59,130,246,0.25)'}`,
              cursor: scraping ? 'wait' : 'pointer',
            }}
          >
            {scraping ? '⏳ Scraping en cours...' : '🔄 Scraper toutes les stats'}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {services.map(s => (
          <div key={s.label} className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs" style={{
            background: s.ok ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.08)',
            color: s.ok ? '#22c55e' : '#ef4444',
            border: `1px solid ${s.ok ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.1)'}`,
          }} title={s.desc}>
            <span>{s.ok ? '✓' : '✗'}</span>
            <span>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}


// ══════════════════════════════════════════════════════
// PAGE PRINCIPALE — CALENDAR VIEW
// ══════════════════════════════════════════════════════
export default function SocialPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [posts, setPosts] = useState<CampaignPost[]>([])
  const [selectedPost, setSelectedPost] = useState<CampaignPost | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNewCampaign, setShowNewCampaign] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null)
  const [view, setView] = useState<'calendrier' | 'analyse' | 'comparaison'>('calendrier')
  const [compareA, setCompareA] = useState('')
  const [compareB, setCompareB] = useState('')
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null)
  const [comparingLoad, setComparingLoad] = useState(false)
  const [showNewPost, setShowNewPost] = useState(false)
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null)
  const [statsStatus, setStatsStatus] = useState<{ configured: boolean; platforms: string[] } | null>(null)
  const [filterPlatform, setFilterPlatform] = useState<string>('')

  const loadCampaigns = useCallback(async () => {
    try {
      const data = await fetchCampaigns()
      setCampaigns(data.campaigns || [])
    } catch (e) { console.error(e) }
    setLoading(false)
  }, [])

  useEffect(() => {
    loadCampaigns()
    fetchPublicationStatus().then(setServiceStatus).catch(() => {})
    fetchSocialStatsStatus().then(setStatsStatus).catch(() => {})
  }, [loadCampaigns])

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

  // Filter posts by platform
  const filteredPosts = useMemo(() => {
    if (!filterPlatform) return posts
    return posts.filter(p =>
      Object.keys(p.platform_stats || {}).some(plat => plat.toLowerCase().includes(filterPlatform.toLowerCase()))
    )
  }, [posts, filterPlatform])

  // Stats globales
  const totalStats = selectedCampaign ? {
    views: selectedCampaign.total_views,
    likes: selectedCampaign.total_likes,
    comments: selectedCampaign.total_comments,
    clicks: selectedCampaign.total_clicks,
    reach: selectedCampaign.total_reach,
    posts: selectedCampaign.post_count,
  } : null

  type SentimentInfo = {
    global?: string
    score?: number
    themes?: string[]
    positive_highlights?: string[]
    negative_highlights?: string[]
  }
  type PerfInfo = {
    best_format?: string
    best_platform?: string
    best_time?: string
    best_day?: string
    top_post?: string
  }
  const sentimentData = analysis?.sentiment as SentimentInfo | undefined
  const perfData = analysis?.performance as PerfInfo | undefined
  const recommendations = (analysis?.recommendations || []) as string[]

  const handleScrapePost = async (pid: string) => {
    try {
      const result = await scrapePostStats(pid)
      if (result.ok) {
        if (selectedCampaign) selectCampaign(selectedCampaign)
      } else {
        alert(`Scraping échoué: ${result.error}`)
      }
    } catch (e) { alert('Erreur: ' + e) }
  }

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <main className="flex-1 p-6 ml-16 md:ml-56">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold" style={{ color: 'var(--text)' }}>Campagnes RS</h1>
            <p className="text-sm opacity-60 mt-1">Calendrier des publications et statistiques</p>
          </div>
          <div className="flex gap-2">
            <button className="btn-glass px-4 py-2 font-medium transition-all hover:scale-105" onClick={() => setShowNewPost(true)}
              style={{ background: 'rgba(34,197,94,0.2)', color: '#22c55e' }}>
              🚀 Nouveau post
            </button>
            <button className="btn-glass px-4 py-2 font-medium transition-all hover:scale-105" onClick={() => setShowNewCampaign(true)}
              style={{ background: 'rgba(59,130,246,0.2)', color: '#3b82f6' }}>
              + Nouvelle campagne
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-5">
          {(['calendrier', 'analyse', 'comparaison'] as const).map(tab => (
            <button key={tab} className="px-4 py-2 rounded-lg text-sm font-medium transition-all"
              style={{
                background: view === tab ? 'rgba(59,130,246,0.25)' : 'rgba(255,255,255,0.03)',
                color: view === tab ? '#3b82f6' : 'var(--text)',
                border: `1px solid ${view === tab ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.08)'}`
              }}
              onClick={() => setView(tab)}>
              {tab === 'calendrier' ? '📅 Calendrier' : tab === 'analyse' ? '📊 Analyse' : '⚖️ Comparaison'}
            </button>
          ))}
        </div>

        {/* Service status */}
        <StatusPanel status={serviceStatus} statsStatus={statsStatus} onGlobalScrape={async () => {
          try {
            const result = await triggerGlobalScrape()
            if (result.ok) {
              alert(`Scraping terminé : ${result.updated || 0} MAJ, ${result.created || 0} créés`)
              if (selectedCampaign) selectCampaign(selectedCampaign)
            } else {
              alert(`Erreur scraping: ${result.error}`)
            }
          } catch (e) { alert('Erreur: ' + e) }
        }} />

        {/* Campaign tabs (horizontal) */}
        {!loading && campaigns.length > 0 && (
          <div className="mb-5 pb-4 overflow-x-auto" style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
            <div className="flex gap-2 min-w-fit">
              {campaigns.map(c => (
                <button
                  key={c._id}
                  className="px-4 py-2 rounded-lg font-medium whitespace-nowrap transition-all hover:scale-105"
                  style={{
                    background: selectedCampaign?._id === c._id ? 'rgba(59,130,246,0.2)' : 'rgba(255,255,255,0.03)',
                    color: selectedCampaign?._id === c._id ? '#3b82f6' : 'var(--text)',
                    border: `1px solid ${selectedCampaign?._id === c._id ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.08)'}`,
                  }}
                  onClick={() => selectCampaign(c)}
                >
                  {c.name}
                  <span className="ml-2 text-xs opacity-60">({c.post_count})</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Main content */}
        <div>
          {!selectedCampaign ? (
            <div className="glass-card p-12 text-center">
              <div className="text-6xl mb-4 opacity-20">📢</div>
              <p className="text-lg opacity-50 font-medium">Sélectionnez une campagne pour commencer</p>
              <p className="text-sm opacity-40 mt-2">Choisissez une campagne dans l'onglet ci-dessus</p>
            </div>
          ) : view === 'calendrier' ? (
            <>
              {/* Stats bar */}
              {totalStats && (
                <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-6">
                  {[
                    { label: 'Posts', value: totalStats.posts, icon: '📝', color: '#8b5cf6' },
                    { label: 'Vues', value: totalStats.views, icon: '👁', color: '#3b82f6' },
                    { label: 'Likes', value: totalStats.likes, icon: '❤️', color: '#ef4444' },
                    { label: 'Commentaires', value: totalStats.comments, icon: '💬', color: '#f59e0b' },
                    { label: 'Clics', value: totalStats.clicks, icon: '🔗', color: '#10b981' },
                    { label: 'Reach', value: totalStats.reach, icon: '📊', color: '#06b6d4' },
                  ].map(s => (
                    <div key={s.label} className="glass-card p-3 text-center" style={{ borderLeft: `3px solid ${s.color}` }}>
                      <div className="text-lg mb-0.5">{s.icon}</div>
                      <div className="text-xl font-bold" style={{ color: s.color }}>{formatNumber(s.value)}</div>
                      <div className="text-[10px] opacity-50">{s.label}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Calendar + channel sidebar layout */}
              <div className="flex gap-4">
                {/* Channel sidebar */}
                <div className="w-48 flex-shrink-0 hidden lg:block">
                  <div className="glass-card p-3 sticky top-6">
                    <h3 className="text-xs font-semibold opacity-50 mb-3 uppercase tracking-wider">Canaux</h3>
                    <ChannelSidebar
                      posts={posts}
                      filterPlatform={filterPlatform}
                      setFilterPlatform={setFilterPlatform}
                    />
                  </div>
                </div>

                {/* Calendar */}
                <div className="flex-1 min-w-0">
                  {/* Mobile platform filter */}
                  <div className="lg:hidden mb-4">
                    <select
                      value={filterPlatform}
                      onChange={e => setFilterPlatform(e.target.value)}
                      className="input-dark w-full"
                    >
                      <option value="">Toutes les plateformes</option>
                      {Object.keys(PLAT_COLORS).map(plat => (
                        <option key={plat} value={plat}>
                          {PLAT_COLORS[plat].icon} {plat.charAt(0).toUpperCase() + plat.slice(1)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <CalendarView
                    posts={filteredPosts}
                    campaigns={campaigns}
                    onViewDetail={setSelectedPost}
                    onScrape={handleScrapePost}
                  />
                </div>
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
                  {sentimentData && (
                    <div className="glass-card p-5">
                      <h3 className="font-semibold mb-3" style={{ color: 'var(--text)' }}>Sentiment</h3>
                      <div className="flex items-center gap-4 mb-3">
                        <span className="text-3xl">{SENTIMENT_COLORS[sentimentData.global || 'neutre']?.icon || '😐'}</span>
                        <div>
                          <div className="font-bold capitalize text-lg" style={{ color: SENTIMENT_COLORS[sentimentData.global || 'neutre']?.color }}>
                            {sentimentData.global}
                          </div>
                          <div className="text-sm opacity-60">Score: {((sentimentData.score || 0) * 100).toFixed(0)}%</div>
                        </div>
                      </div>
                      {sentimentData.themes && sentimentData.themes.length > 0 && (
                        <div className="flex flex-wrap gap-2 mb-2">
                          {sentimentData.themes.map((t, i) => (
                            <span key={i} className="px-2 py-1 rounded-full text-xs" style={{ background: 'rgba(59,130,246,0.15)', color: 'var(--text)' }}>{t}</span>
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
                          <div key={p.label} className="p-3 rounded-lg text-center" style={{ background: 'rgba(255,255,255,0.05)' }}>
                            <div className="text-xl mb-1">{p.icon}</div>
                            <div className="font-semibold text-sm capitalize" style={{ color: 'var(--text)' }}>{p.value || '—'}</div>
                            <div className="text-xs opacity-50">{p.label}</div>
                          </div>
                        ))}
                      </div>
                      {perfData.top_post && (
                        <p className="mt-3 text-sm opacity-70">🏆 Top post : <b>{perfData.top_post}</b></p>
                      )}
                    </div>
                  )}

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

        {showNewCampaign && (
          <NewCampaignModal onClose={() => setShowNewCampaign(false)} onCreated={loadCampaigns} />
        )}
        {showNewPost && (
          <NewPostModal
            campaigns={campaigns}
            selectedCampaignId={selectedCampaign?._id}
            onClose={() => setShowNewPost(false)}
            onPublished={() => {
              if (selectedCampaign) selectCampaign(selectedCampaign)
              loadCampaigns()
            }}
          />
        )}
        {selectedPost && (
          <PostDetailModal
            post={selectedPost}
            onClose={() => setSelectedPost(null)}
            onScrape={async (pid) => {
              try {
                const result = await scrapePostStats(pid)
                if (result.ok) {
                  if (selectedCampaign) selectCampaign(selectedCampaign)
                  const updatedPost = filteredPosts.find(p => p._id === pid)
                  if (updatedPost) setSelectedPost(updatedPost)
                } else {
                  alert(`Scraping échoué: ${result.error}`)
                }
              } catch (e) { alert('Erreur: ' + e) }
            }}
          />
        )}
      </main>
    </div>
  )
}
