'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../components/Sidebar'
import BmgGauge from '../components/BmgGauge'
import GuadeloupeMap from '../components/GuadeloupeMap'
import {
  fetchEnrichedDashboard,
  fetchAffairsByCommune,
  runFullCycle,
  runReaffiliate,
  runScrapeNow,
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

function themeColor(theme: string): string {
  const map: Record<string, string> = {
    politique: '#facc15', economie: '#34d399', social: '#93c5fd',
    environnement: '#86efac', sante: '#fda4af', justice: '#fde68a',
    securite: '#fca5a5', education: '#93c5fd', culture: '#f9a8d4',
    sport: '#67e8f9', infrastructure: '#fdba74', general: '#cbd5e1',
    economie_emploi: '#34d399', eau_env: '#86efac',
    energie_transports: '#fdba74', sante_social: '#fda4af',
    securite_justice: '#fde68a', culture_patrimoine: '#f9a8d4',
  }
  return map[theme] || '#cbd5e1'
}

function themeColorParts(theme: string): [string, string, string] {
  const map: Record<string, string> = {
    politique: 'rgba(22,163,74,0.12)_#facc15_rgba(22,163,74,0.25)',
    economie: 'rgba(16,185,129,0.12)_#34d399_rgba(16,185,129,0.25)',
    social: 'rgba(96,165,250,0.12)_#93c5fd_rgba(96,165,250,0.25)',
    environnement: 'rgba(74,222,128,0.12)_#86efac_rgba(74,222,128,0.25)',
    sante: 'rgba(251,113,133,0.12)_#fda4af_rgba(251,113,133,0.25)',
    justice: 'rgba(251,191,36,0.12)_#fde68a_rgba(251,191,36,0.25)',
    securite: 'rgba(248,113,113,0.12)_#fca5a5_rgba(248,113,113,0.25)',
    education: 'rgba(129,140,248,0.12)_#93c5fd_rgba(129,140,248,0.25)',
    culture: 'rgba(244,114,182,0.12)_#f9a8d4_rgba(244,114,182,0.25)',
    sport: 'rgba(34,211,238,0.12)_#67e8f9_rgba(34,211,238,0.25)',
    infrastructure: 'rgba(251,146,60,0.12)_#fdba74_rgba(251,146,60,0.25)',
  }
  const raw = map[theme] || 'rgba(148,163,184,0.12)_#cbd5e1_rgba(148,163,184,0.25)'
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
  if (pct === 0) return <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>—</span>
  const up = pct > 0
  return (
    <span className="text-[10px] font-semibold flex items-center gap-0.5" style={{ color: up ? '#34d399' : '#f87171' }}>
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"
        style={{ transform: up ? 'rotate(0)' : 'rotate(180deg)' }}>
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
      </svg>
      {Math.abs(pct)}%
    </span>
  )
}

// ── Sentiment Arc Gauge ─────────────────────────────────
function SentimentGauge({ sentimentDist }: { sentimentDist: Record<string, number> }) {
  const entries = Object.entries(sentimentDist)
  const total = entries.reduce((s, [, c]) => s + c, 0)
  if (total === 0) return <div className="text-center py-8 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Pas de données</div>

  const positif = (sentimentDist['positif'] || sentimentDist['positive'] || 0)
  const negatif = (sentimentDist['négatif'] || sentimentDist['negatif'] || sentimentDist['negative'] || 0)
  const neutre = (sentimentDist['neutre'] || sentimentDist['neutral'] || 0)
  const mixte = (sentimentDist['mixte'] || sentimentDist['mixed'] || 0)

  // Global sentiment score: 0-100 where 50=neutral, >50=positive, <50=negative
  const score = total > 0
    ? Math.round(((positif * 100 + neutre * 55 + mixte * 50 + negatif * 10) / total))
    : 50

  // Arc: 180 degrees, score maps to position
  const angle = (score / 100) * 180
  const r = 70
  const cx = 80, cy = 80

  // Arc path for background
  const arcPath = (startAngle: number, endAngle: number) => {
    const s = (startAngle - 180) * Math.PI / 180
    const e = (endAngle - 180) * Math.PI / 180
    const x1 = cx + r * Math.cos(s)
    const y1 = cy + r * Math.sin(s)
    const x2 = cx + r * Math.cos(e)
    const y2 = cy + r * Math.sin(e)
    const large = endAngle - startAngle > 180 ? 1 : 0
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
  }

  // Needle position
  const needleAngle = (angle - 180) * Math.PI / 180
  const needleLen = r - 8
  const nx = cx + needleLen * Math.cos(needleAngle)
  const ny = cy + needleLen * Math.sin(needleAngle)

  const moodEmoji = score >= 70 ? '😊' : score >= 50 ? '😐' : score >= 30 ? '😟' : '😡'
  const moodLabel = score >= 70 ? 'Positif' : score >= 50 ? 'Neutre' : score >= 30 ? 'Tendu' : 'Négatif'
  const moodColor = score >= 70 ? '#34d399' : score >= 50 ? '#60a5fa' : score >= 30 ? '#fbbf24' : '#f87171'

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 160 95" className="w-full max-w-[200px]">
        {/* Background arc segments */}
        <path d={arcPath(0, 60)} fill="none" stroke="#f87171" strokeWidth="10" strokeLinecap="round" opacity="0.15" />
        <path d={arcPath(60, 120)} fill="none" stroke="#fbbf24" strokeWidth="10" strokeLinecap="round" opacity="0.15" />
        <path d={arcPath(120, 180)} fill="none" stroke="#34d399" strokeWidth="10" strokeLinecap="round" opacity="0.15" />

        {/* Active arc */}
        <path d={arcPath(0, angle)} fill="none" stroke={moodColor} strokeWidth="10" strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${moodColor}50)` }} />

        {/* Needle */}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.8" />
        <circle cx={cx} cy={cy} r="4" fill="white" opacity="0.9" />

        {/* Score text */}
        <text x={cx} y={cy - 12} textAnchor="middle" fill="white" fontSize="22" fontWeight="bold">{score}</text>
        <text x={cx} y={cy - 0} textAnchor="middle" fill={moodColor} fontSize="8" fontWeight="500">{moodLabel}</text>
      </svg>

      <div className="text-2xl mt-1">{moodEmoji}</div>

      {/* Mini breakdown */}
      <div className="flex items-center gap-3 mt-3">
        {[
          { label: 'Positif', count: positif, color: '#34d399' },
          { label: 'Neutre', count: neutre, color: '#60a5fa' },
          { label: 'Négatif', count: negatif, color: '#f87171' },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
            <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.35)' }}>
              {s.label} <span style={{ color: s.color }}>{total > 0 ? Math.round(s.count / total * 100) : 0}%</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Top Personalities ──────────────────────────────────
function TopPersonalities({ entities }: { entities: TopEntity[] }) {
  const colors = ['#60a5fa', '#34d399', '#facc15', '#f87171', '#c084fc', '#fb923c', '#67e8f9', '#f9a8d4']

  if (entities.length === 0) return <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune entité</p>

  return (
    <div className="space-y-2">
      {entities.slice(0, 8).map((e, i) => {
        const color = colors[i % colors.length]
        const maxC = entities[0].count
        const initials = e.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
        return (
          <div key={i} className="flex items-center gap-3 group">
            {/* Avatar */}
            <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold"
              style={{
                background: `${color}18`,
                border: `1.5px solid ${color}40`,
                color: color,
              }}>
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs truncate font-medium group-hover:text-white/80 transition-colors" style={{ color: 'rgba(255,255,255,0.55)' }}>{e.name}</span>
                <span className="text-[10px] ml-2 flex-shrink-0 font-semibold" style={{ color }}>{e.count}</span>
              </div>
              <div className="h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.03)' }}>
                <div className="h-full rounded-full transition-all duration-700" style={{
                  width: `${(e.count / maxC) * 100}%`,
                  background: `linear-gradient(90deg, ${color}80, ${color})`,
                  boxShadow: `0 0 6px ${color}20`,
                }} />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Trending Topics ────────────────────────────────────
function TrendingTopics({ themes }: { themes: Record<string, number> }) {
  const sorted = Object.entries(themes).sort(([, a], [, b]) => b - a)
  if (sorted.length === 0) return <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune donnée</p>

  const maxCount = sorted[0][1]

  return (
    <div className="space-y-3">
      {sorted.slice(0, 8).map(([theme, count], i) => {
        const color = themeColor(theme)
        const pct = Math.round((count / maxCount) * 100)
        return (
          <div key={theme}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold w-4 text-center" style={{ color: 'rgba(255,255,255,0.15)' }}>#{i + 1}</span>
                <span className="text-xs font-medium" style={{ color: 'rgba(255,255,255,0.55)' }}>{themeLabel(theme)}</span>
              </div>
              <span className="text-[11px] font-bold" style={{ color }}>{count} affaire{count > 1 ? 's' : ''}</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <div className="h-full rounded-full transition-all duration-1000" style={{
                width: `${pct}%`,
                background: `linear-gradient(90deg, ${color}90, ${color})`,
                boxShadow: `0 0 8px ${color}30`,
              }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Activity Heatmap (7 days x hours) ──────────────────
function ActivityMiniChart({ data }: { data: DailyActivity[] }) {
  const maxArticles = Math.max(...data.map(d => d.articles), 1)
  return (
    <div className="flex items-end gap-2 h-32">
      {data.map((d, i) => {
        const h = (d.articles / maxArticles) * 100
        const isToday = i === data.length - 1
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1.5 group relative">
            {/* Tooltip */}
            <div className="absolute -top-8 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-all duration-200
              px-2.5 py-1 rounded-lg text-[9px] font-medium whitespace-nowrap z-10 pointer-events-none"
              style={{ background: 'rgba(37,99,235,0.95)', color: 'white', boxShadow: '0 4px 12px rgba(37,99,235,0.3)' }}>
              {d.articles} articles · {d.events} événements
            </div>
            {/* Bar */}
            <div className="w-full rounded-t-md transition-all duration-700 group-hover:brightness-125 relative"
              style={{
                height: `${Math.max(h, 4)}%`,
                background: isToday
                  ? 'linear-gradient(180deg, #facc15 0%, #f59e0b 100%)'
                  : `linear-gradient(180deg, #60a5fa 0%, #1d4ed8 100%)`,
                boxShadow: isToday ? '0 -2px 12px rgba(245,158,11,0.3)' : d.articles > 0 ? '0 -2px 12px rgba(37,99,235,0.15)' : 'none',
                borderRadius: '4px 4px 2px 2px',
              }}>
              {/* Value on top */}
              {d.articles > 0 && (
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] font-bold opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ color: isToday ? '#facc15' : '#60a5fa' }}>
                  {d.articles}
                </span>
              )}
            </div>
            {/* Day label */}
            <span className={`text-[9px] leading-none font-medium ${isToday ? 'text-white/60' : ''}`}
              style={{ color: isToday ? undefined : 'rgba(255,255,255,0.2)' }}>
              {d.label.split(' ')[0]}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Major Stories Carousel ─────────────────────────────
function MajorStories({ affairs }: { affairs: Affair[] }) {
  const [idx, setIdx] = useState(0)
  const stories = affairs.slice(0, 5)

  useEffect(() => {
    if (stories.length <= 1) return
    const timer = setInterval(() => setIdx(i => (i + 1) % stories.length), 6000)
    return () => clearInterval(timer)
  }, [stories.length])

  if (stories.length === 0) {
    return <div className="text-center py-10 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune affaire majeure</div>
  }

  const affair = stories[idx]
  const priority = affair.priority || 'minor'
  const accentColor = priority === 'hot' ? '#f87171' : priority === 'watch' ? '#fbbf24' : '#34d399'

  return (
    <div className="relative">
      {/* Story card */}
      <Link href={`/affairs/${affair._id}`}>
        <div className="group cursor-pointer transition-all duration-500">
          <div className="flex items-start gap-4">
            {/* BMG */}
            <div className="flex-shrink-0">
              <BmgGauge value={(affair.bmg || 0) * 100} size={56} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                {priority === 'hot' && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold animate-pulse"
                    style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}>
                    URGENT
                  </span>
                )}
                <ThemeBadge theme={affair.theme} />
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{timeAgo(affair.last_activity || affair.created_at)}</span>
              </div>
              <h3 className="text-sm font-semibold text-white group-hover:text-blue-300 transition-colors line-clamp-2 mb-1.5">
                {affair.title || affair.primary_entity || 'Affaire'}
              </h3>
              {affair.description && (
                <p className="text-[11px] line-clamp-2 leading-relaxed" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  {affair.description}
                </p>
              )}
              <div className="flex items-center gap-3 mt-2">
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>
                  {affair.item_count || 0} sources
                </span>
                <span className="text-[10px] font-semibold" style={{ color: accentColor }}>
                  Gravité {Math.round((affair.gravity_score || 0) * 100)}%
                </span>
                {affair.sentiment && (
                  <span className="text-[10px] capitalize" style={{
                    color: affair.sentiment === 'positif' ? '#34d399' : affair.sentiment === 'négatif' ? '#f87171' : '#60a5fa'
                  }}>{affair.sentiment}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </Link>

      {/* Dots navigation */}
      {stories.length > 1 && (
        <div className="flex items-center justify-center gap-1.5 mt-4">
          {stories.map((_, i) => (
            <button key={i} onClick={() => setIdx(i)}
              className="transition-all duration-300"
              style={{
                width: i === idx ? 16 : 6,
                height: 6,
                borderRadius: 3,
                background: i === idx ? accentColor : 'rgba(255,255,255,0.1)',
                boxShadow: i === idx ? `0 0 8px ${accentColor}40` : 'none',
              }} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Affair Timeline (chronologie) ──────────────────────
function AffairTimeline({ affairs }: { affairs: Affair[] }) {
  // Sort by creation date, most recent first
  const sorted = [...affairs]
    .filter(a => a.created_at)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 12)

  if (sorted.length === 0) {
    return <div className="text-center py-6 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune affaire</div>
  }

  // Find time range
  const now = Date.now()
  const oldest = new Date(sorted[sorted.length - 1].created_at).getTime()
  const range = Math.max(now - oldest, 86400000) // min 1 day range

  const priorityColor = (p: string) =>
    p === 'hot' ? '#f87171' : p === 'watch' ? '#fbbf24' : '#34d399'

  return (
    <div className="relative">
      {/* Time axis */}
      <div className="h-px w-full mb-1" style={{ background: 'rgba(255,255,255,0.06)' }} />

      {/* Time labels */}
      <div className="flex justify-between mb-4">
        <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.15)' }}>
          {new Date(oldest).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
        </span>
        <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.15)' }}>Aujourd'hui</span>
      </div>

      {/* Affair items */}
      <div className="space-y-2">
        {sorted.map((affair) => {
          const created = new Date(affair.created_at).getTime()
          const lastAct = affair.last_activity ? new Date(affair.last_activity).getTime() : created
          const startPct = ((created - oldest) / range) * 100
          const endPct = Math.min(((lastAct - oldest) / range) * 100, 100)
          const widthPct = Math.max(endPct - startPct, 2)
          const color = priorityColor(affair.priority || 'minor')
          const tc = themeColor(affair.theme)

          return (
            <Link key={affair._id} href={`/affairs/${affair._id}`}>
              <div className="group flex items-center gap-2 cursor-pointer hover:bg-white/[0.02] rounded-lg px-2 py-1.5 transition-all">
                {/* Title */}
                <div className="w-32 lg:w-40 flex-shrink-0">
                  <p className="text-[11px] truncate font-medium group-hover:text-white/80 transition-colors" style={{ color: 'rgba(255,255,255,0.45)' }}>
                    {affair.title || affair.primary_entity || '—'}
                  </p>
                  <p className="text-[9px]" style={{ color: 'rgba(255,255,255,0.12)' }}>
                    {timeAgo(affair.created_at)}
                  </p>
                </div>

                {/* Timeline bar */}
                <div className="flex-1 h-5 relative rounded-sm" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <div className="absolute h-full rounded-sm transition-all duration-500 group-hover:brightness-125 flex items-center"
                    style={{
                      left: `${startPct}%`,
                      width: `${widthPct}%`,
                      minWidth: 8,
                      background: `linear-gradient(90deg, ${color}60, ${color})`,
                      boxShadow: `0 0 6px ${color}20`,
                    }}>
                    {widthPct > 15 && (
                      <span className="text-[8px] font-bold px-1 truncate" style={{ color: 'white' }}>
                        {affair.item_count || 0}
                      </span>
                    )}
                  </div>
                </div>

                {/* BMG badge */}
                <div className="w-10 text-right flex-shrink-0">
                  <span className="text-[10px] font-bold" style={{ color }}>
                    {Math.round((affair.bmg || 0) * 100)}
                  </span>
                </div>
              </div>
            </Link>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-3 justify-center">
        {[
          { label: 'Urgente', color: '#f87171' },
          { label: 'Suivi', color: '#fbbf24' },
          { label: 'Mineure', color: '#34d399' },
        ].map(l => (
          <div key={l.label} className="flex items-center gap-1">
            <div className="w-3 h-1.5 rounded-sm" style={{ background: l.color }} />
            <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Gravity Donut (kept from original) ────────────────
function GravityDonut({ distribution }: {
  distribution: { low: number; medium: number; high: number; critical: number }
}) {
  const total = distribution.low + distribution.medium + distribution.high + distribution.critical
  if (total === 0) return <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Pas de données</p>

  const segments = [
    { key: 'low', label: 'Faible', count: distribution.low, color: '#34d399' },
    { key: 'medium', label: 'Moyen', count: distribution.medium, color: '#fbbf24' },
    { key: 'high', label: 'Élevé', count: distribution.high, color: '#fb923c' },
    { key: 'critical', label: 'Critique', count: distribution.critical, color: '#f87171' },
  ]

  const radius = 36, cx = 45, cy = 45
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
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 90 90" className="w-20 h-20 flex-shrink-0" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={cx} cy={cy} r={radius} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="10" />
        {arcs.map(a => (
          <circle key={a.key} cx={cx} cy={cy} r={radius} fill="none"
            stroke={a.color} strokeWidth="10"
            strokeDasharray={a.dasharray} strokeDashoffset={a.dashoffset}
            strokeLinecap="butt"
            style={{ filter: `drop-shadow(0 0 3px ${a.color}40)` }} />
        ))}
        <text x={cx} y={cy + 4} textAnchor="middle" fill="white" fontSize="14" fontWeight="bold"
          style={{ transform: 'rotate(90deg)', transformOrigin: '50% 50%' }}>
          {total}
        </text>
      </svg>
      <div className="space-y-1 flex-1">
        {segments.map(s => (
          <div key={s.key} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
            <span className="text-[10px] flex-1" style={{ color: 'rgba(255,255,255,0.4)' }}>{s.label}</span>
            <span className="text-[10px] font-semibold" style={{ color: s.color }}>
              {s.count} <span style={{ color: 'rgba(255,255,255,0.12)' }}>({total > 0 ? Math.round(s.count / total * 100) : 0}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Skeleton ────────────────────────────────
function SkeletonCard() {
  return (
    <div className="glass-card-static p-5">
      <div className="skeleton h-3 w-20 mb-3" />
      <div className="skeleton h-8 w-14 mb-2" />
      <div className="skeleton h-2 w-16" />
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
  const [communeMapData, setCommuneMapData] = useState<Record<string, { count: number; maxGravity: number; affairs: Array<{ _id: string; title: string; gravity_score: number; sentiment: string; theme: string }> }>>({})
  const [selectedCommune, setSelectedCommune] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [result, mapRes] = await Promise.all([
        fetchEnrichedDashboard(),
        fetchAffairsByCommune().catch(() => ({ communes: {} })),
      ])
      setData(result)
      setCommuneMapData(mapRes.communes || {})
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
        <main className="lg:ml-60 flex-1 p-6 min-h-screen">
          <div className="max-w-[1440px] mx-auto">
            <div className="skeleton h-7 w-44 mb-8" />
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
              {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="glass-card-static p-5"><div className="skeleton h-3 w-28 mb-4" /><div className="skeleton h-28 w-full" /></div>
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

  return (
    <div className="flex">
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-4 lg:p-6 min-h-screen">
        <div className="max-w-[1440px] mx-auto animate-fade-in">

          {/* ── HEADER ───────────────────────────────────── */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
            <div>
              <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight flex items-center gap-2">
                Tableau de bord
                <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                  style={{ background: 'rgba(22,163,74,0.1)', color: '#34d399', border: '1px solid rgba(22,163,74,0.2)' }}>
                  LIVE
                </span>
              </h1>
              <p className="text-[11px] mt-0.5 font-medium" style={{ color: 'rgba(255,255,255,0.2)' }}>
                MAJ {lastRefresh.toLocaleTimeString('fr-FR')} — 7 derniers jours
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={loadData} className="btn-glass px-3 py-1.5 text-xs">
                <span className="flex items-center gap-1.5">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                  Rafraîchir
                </span>
              </button>
              <button onClick={handleScrape} disabled={scraping} className="btn-glass px-3 py-1.5 text-xs disabled:opacity-40"
                style={scraping ? { background: 'rgba(37,99,235,0.12)', borderColor: 'rgba(37,99,235,0.25)' } : {}}>
                {scraping ? '⟳ Scraping...' : 'Scraper'}
              </button>
              <button onClick={handleBulkEnrich} disabled={bulkEnriching} className="btn-glass px-3 py-1.5 text-xs disabled:opacity-40"
                style={bulkEnriching ? { background: 'rgba(234,179,8,0.12)', borderColor: 'rgba(234,179,8,0.25)' } : {}}>
                {bulkEnriching ? '⟳ Enrichir...' : 'Enrichir'}
              </button>
              <button onClick={handleRunCycle} disabled={cycleRunning} className="btn-primary px-4 py-1.5 text-xs">
                {cycleRunning ? '⟳ Cycle...' : '▶ Lancer le cycle'}
              </button>
            </div>
            {bulkMsg && <div className="text-xs mt-1 text-right" style={{ color: 'rgba(234,179,8,0.6)' }}>{bulkMsg}</div>}
          </div>

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl text-sm" style={{
              background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)', color: '#f87171'
            }}>{error}</div>
          )}

          {/* ── Alertes critiques ─────────────────────── */}
          {criticals.length > 0 && (
            <div className="mb-5">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" style={{ boxShadow: '0 0 8px rgba(239,68,68,0.5)' }} />
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#f87171' }}>Alertes ({criticals.length})</h2>
              </div>
              <div className="space-y-1.5">
                {criticals.slice(0, 3).map((a) => (
                  <Link key={a._id} href={`/affairs/${a._id}`}>
                    <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl cursor-pointer transition-all hover:translate-x-1"
                      style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.12)' }}>
                      <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse flex-shrink-0" style={{ boxShadow: '0 0 8px rgba(239,68,68,0.4)' }} />
                      <p className="text-sm font-medium text-white truncate flex-1">{a.title || a.primary_entity}</p>
                      <span className="text-xs font-semibold flex-shrink-0" style={{ color: '#f87171' }}>BMG {Math.round((a.bmg || 0) * 100)}</span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* ═══ ROW 1 : KPI Strip ═══════════════════════ */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5 stagger-fade">
            {/* Affaires actives */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1 font-semibold" style={{ color: 'rgba(255,255,255,0.25)' }}>Affaires actives</p>
              <div className="flex items-baseline gap-2">
                <p className="text-3xl font-bold" style={{ color: '#60a5fa' }}>{stats?.affairs_active ?? 0}</p>
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.15)' }}>{stats?.affairs_stale ?? 0} veille</span>
              </div>
              {(priorityCounts.hot || 0) > 0 && (
                <div className="flex items-center gap-1.5 mt-2">
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold" style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}>
                    {priorityCounts.hot} urgente{(priorityCounts.hot || 0) > 1 ? 's' : ''}
                  </span>
                </div>
              )}
            </div>

            {/* Articles 7j */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1 font-semibold" style={{ color: 'rgba(255,255,255,0.25)' }}>Articles 7j</p>
              <div className="flex items-baseline gap-2">
                <p className="text-3xl font-bold text-white">{coverage?.total_articles_7d ?? 0}</p>
                {trends && <TrendArrow pct={trends.articles_trend_pct} />}
              </div>
              <p className="text-[10px] mt-0.5" style={{ color: 'rgba(255,255,255,0.15)' }}>{coverage?.enriched_articles_7d ?? 0} enrichis</p>
            </div>

            {/* BMG Moyen */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1 font-semibold" style={{ color: 'rgba(255,255,255,0.25)' }}>BMG moyen</p>
              <div className="flex items-center gap-3">
                <BmgGauge value={avgBmg * 100} size={48} />
                <div>
                  <p className="text-2xl font-bold text-white">{Math.round(avgBmg * 100)}</p>
                  <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.15)' }}>/ 100</p>
                </div>
              </div>
            </div>

            {/* Radio + Social */}
            <div className="glass-card-static p-4">
              <p className="text-[10px] uppercase tracking-wider mb-1 font-semibold" style={{ color: 'rgba(255,255,255,0.25)' }}>Radio & Sources</p>
              <div className="flex items-baseline gap-2">
                <p className="text-3xl font-bold" style={{ color: '#facc15' }}>{coverage?.total_transcriptions_7d ?? 0}</p>
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.15)' }}>transcriptions</span>
              </div>
              <div className="h-1 rounded-full mt-2" style={{ background: 'rgba(255,255,255,0.03)' }}>
                <div className="h-full rounded-full transition-all duration-1000" style={{
                  width: `${Math.min(100, coverage?.affiliation_rate ?? 0)}%`,
                  background: 'linear-gradient(90deg, #16a34a, #facc15)',
                  boxShadow: '0 0 6px rgba(22,163,74,0.3)',
                }} />
              </div>
              <p className="text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.15)' }}>{coverage?.affiliation_rate ?? 0}% affiliés</p>
            </div>
          </div>

          {/* ═══ ROW 2 : Sentiment + Top Personnalités + Trending ═══ */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5 stagger-fade">
            {/* Sentiment Gauge */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.35)' }}>
                Climat médiatique
              </h2>
              <SentimentGauge sentimentDist={sentimentDist} />
            </div>

            {/* Top Personnalités */}
            <div className="glass-card-static p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  Top personnalités
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.25)' }}>
                  {entities.length} détectées
                </span>
              </div>
              <TopPersonalities entities={entities} />
            </div>

            {/* Trending Topics */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.35)' }}>
                Sujets tendance
              </h2>
              <TrendingTopics themes={themes} />
            </div>
          </div>

          {/* ═══ ROW 3 : Major Story + Activity Chart + Gravity ═══ */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
            {/* Major Story */}
            <div className="glass-card-static p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  Affaire du moment
                </h2>
                <Link href="/affairs" className="text-[10px] font-medium transition-colors hover:text-blue-300" style={{ color: '#60a5fa' }}>
                  Tout voir →
                </Link>
              </div>
              <MajorStories affairs={topAffairs} />
            </div>

            {/* Activity Chart */}
            <div className="glass-card-static p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>Activité 7 jours</h2>
                {trends && (
                  <div className="flex items-center gap-1">
                    <TrendArrow pct={trends.articles_trend_pct} />
                    <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.15)' }}>vs sem.</span>
                  </div>
                )}
              </div>
              {activity.length > 0 ? (
                <ActivityMiniChart data={activity} />
              ) : (
                <p className="text-xs text-center py-8" style={{ color: 'rgba(255,255,255,0.2)' }}>Pas de données</p>
              )}
              <div className="flex items-center gap-4 mt-3 justify-center">
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-sm" style={{ background: 'linear-gradient(135deg, #60a5fa, #1d4ed8)' }} />
                  <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.2)' }}>Articles</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-sm" style={{ background: 'linear-gradient(135deg, #facc15, #f59e0b)' }} />
                  <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.2)' }}>Aujourd'hui</span>
                </div>
              </div>
            </div>

            {/* Gravity Distribution */}
            <div className="glass-card-static p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'rgba(255,255,255,0.35)' }}>Gravité des affaires</h2>
              {gravityDist ? (
                <GravityDonut distribution={gravityDist} />
              ) : (
                <p className="text-xs text-center py-8" style={{ color: 'rgba(255,255,255,0.2)' }}>Pas de données</p>
              )}
            </div>
          </div>

          {/* ═══ ROW 4 : Carte Guadeloupe + Sources ═══════ */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-5">
            <div className="xl:col-span-2 glass-card-static p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  Carte des affaires
                </h2>
                {selectedCommune && (
                  <button onClick={() => setSelectedCommune(null)}
                    className="text-[10px] px-2 py-0.5 rounded-full transition-all hover:scale-105"
                    style={{ background: 'rgba(37,99,235,0.12)', color: '#93c5fd', border: '1px solid rgba(37,99,235,0.25)' }}>
                    ✕ {selectedCommune}
                  </button>
                )}
              </div>
              <GuadeloupeMap
                communeData={Object.fromEntries(
                  Object.entries(communeMapData).map(([k, v]) => [k, { count: v.count, maxGravity: v.maxGravity }])
                )}
                onCommuneClick={(c) => setSelectedCommune(prev => prev === c ? null : c)}
              />
            </div>

            <div className="glass-card-static p-5">
              {selectedCommune ? (
                <>
                  <h2 className="text-xs font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-blue-500" style={{ boxShadow: '0 0 6px rgba(37,99,235,0.4)' }} />
                    {selectedCommune}
                  </h2>
                  {(communeMapData[selectedCommune]?.affairs || []).length === 0 ? (
                    <p className="text-xs py-6 text-center" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune affaire active</p>
                  ) : (
                    <div className="space-y-2">
                      {(communeMapData[selectedCommune]?.affairs || []).map((a) => (
                        <Link key={a._id} href={`/affairs/${a._id}`}>
                          <div className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-white/[0.04] transition-all cursor-pointer group">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                              a.gravity_score >= 0.7 ? 'bg-red-500/15 text-red-400'
                              : a.gravity_score >= 0.5 ? 'bg-orange-500/15 text-orange-400'
                              : 'bg-emerald-500/15 text-emerald-400'
                            }`}>
                              {Math.round(a.gravity_score * 100)}%
                            </span>
                            <span className="text-xs text-white/80 truncate flex-1 group-hover:text-white transition-colors">{a.title}</span>
                          </div>
                        </Link>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <>
                  <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255,255,255,0.35)' }}>
                    Sources actives 7j
                  </h2>
                  {sources.length > 0 ? (
                    <div className="space-y-2">
                      {sources.map((s, i) => {
                        const maxC = sources[0].count
                        return (
                          <div key={i}>
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-[11px] truncate" style={{ color: 'rgba(255,255,255,0.45)' }}>{s.name}</span>
                              <span className="text-[11px] font-semibold text-white/80">{s.count}</span>
                            </div>
                            <div className="h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.03)' }}>
                              <div className="h-full rounded-full" style={{
                                width: `${(s.count / maxC) * 100}%`,
                                background: 'linear-gradient(90deg, #1d4ed8, #60a5fa)',
                                boxShadow: '0 0 4px rgba(37,99,235,0.2)',
                              }} />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune source</p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* ═══ ROW 5 : Top Affaires Grid ════════════════ */}
          <div className="mb-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white">Affaires majeures</h2>
              <Link href="/affairs" className="text-xs font-medium transition-colors hover:text-blue-300" style={{ color: '#60a5fa' }}>Voir tout →</Link>
            </div>
            {topAffairs.length === 0 ? (
              <div className="glass-card-static p-10 text-center">
                <p className="text-sm" style={{ color: 'rgba(255,255,255,0.3)' }}>Aucune affaire active</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 stagger-fade">
                {topAffairs.slice(0, 8).map((affair) => {
                  const priority = affair.priority || 'minor'
                  const borderColor = priority === 'hot' ? '#f87171' : priority === 'watch' ? '#fbbf24' : '#34d399'
                  return (
                    <Link key={affair._id} href={`/affairs/${affair._id}`}>
                      <div className="glass-card p-4 cursor-pointer h-full group" style={{ borderLeft: `2px solid ${borderColor}` }}>
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="flex-1 min-w-0">
                            <h3 className="text-sm font-semibold text-white truncate group-hover:text-blue-300 transition-colors">
                              {affair.title || affair.primary_entity || 'Affaire'}
                            </h3>
                            {affair.primary_entity && affair.title !== affair.primary_entity && (
                              <p className="text-[10px] truncate mt-0.5" style={{ color: 'rgba(255,255,255,0.25)' }}>{affair.primary_entity}</p>
                            )}
                          </div>
                          <BmgGauge value={(affair.bmg || 0) * 100} size={44} />
                        </div>
                        <div className="flex flex-wrap gap-1 mb-2">
                          <ThemeBadge theme={affair.theme} />
                          <span className="text-[10px] px-2 py-0.5 rounded-full"
                            style={{ background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.3)' }}>
                            {affair.item_count || 0} sources
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>
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

          {/* ═══ ROW 5b : Chronologie des affaires ════════ */}
          {topAffairs.length > 0 && (
            <div className="glass-card-static p-5 mb-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  Chronologie des affaires
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.2)' }}>
                  Durée de vie & activité
                </span>
              </div>
              <AffairTimeline affairs={topAffairs} />
            </div>
          )}

          {/* ═══ ROW 6 : Orphelins + Timeline ════════════ */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
            <div className="lg:col-span-2">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h2 className="text-sm font-semibold text-white">Articles non affiliés</h2>
                  <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>Enrichis mais sans affaire</p>
                </div>
                <div className="flex items-center gap-2">
                  {orphans.length > 0 && (
                    <span className="text-xs px-2 py-1 rounded-full font-medium" style={{
                      background: 'rgba(245,158,11,0.08)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.15)'
                    }}>{orphans.length} orphelins</span>
                  )}
                  <button onClick={handleReaffiliate} disabled={reaffiliating} className="btn-glass text-xs px-3 py-1 disabled:opacity-40">
                    {reaffiliating ? '⟳ En cours...' : 'Ré-affilier'}
                  </button>
                </div>
              </div>
              {orphans.length > 0 ? (
                <div className="glass-card-static overflow-hidden">
                  {orphans.slice(0, 10).map((art, idx) => (
                    <div key={art._id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.02] transition-colors"
                      style={{ borderBottom: idx < Math.min(orphans.length, 10) - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none' }}>
                      <ThemeBadge theme={art.theme} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs truncate" style={{ color: 'rgba(255,255,255,0.55)' }}>{art.title}</p>
                        <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{art.source} — {timeAgo(art.scraped_at)}</p>
                      </div>
                      <div className="flex-shrink-0 text-right">
                        <p className="text-xs font-bold" style={{
                          color: art.gravity_score >= 0.7 ? '#f87171' : art.gravity_score >= 0.4 ? '#fbbf24' : 'rgba(255,255,255,0.25)'
                        }}>{Math.round(art.gravity_score * 100)}%</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="glass-card-static p-6 text-center">
                  <p className="text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Tous les articles sont affiliés</p>
                </div>
              )}
            </div>

            {/* Timeline */}
            <div className="glass-card-static p-4">
              <h3 className="text-[10px] uppercase tracking-wider mb-3 font-semibold" style={{ color: 'rgba(255,255,255,0.25)' }}>
                Activité récente
              </h3>
              {timeline.length > 0 ? (
                <div className="relative">
                  {/* Vertical line */}
                  <div className="absolute left-[5px] top-2 bottom-2 w-px" style={{ background: 'rgba(255,255,255,0.05)' }} />
                  <div className="space-y-1">
                    {timeline.slice(0, 12).map((evt) => {
                      const colorMap: Record<string, string> = {
                        created: '#60a5fa', article_added: '#34d399', radio_topic_added: '#facc15',
                        gravity_update: '#fbbf24', archived: '#64748b', expired: '#64748b', bmg_change: '#fb923c',
                      }
                      const evtColor = colorMap[evt.event] || '#64748b'
                      return (
                        <div key={evt._id} className="flex items-start gap-3 py-1.5 group relative pl-1">
                          <div className="w-2.5 h-2.5 rounded-full flex-shrink-0 mt-0.5 relative z-10" style={{
                            background: evtColor,
                            boxShadow: `0 0 6px ${evtColor}30`,
                          }} />
                          <div className="flex-1 min-w-0">
                            <p className="text-[11px] truncate group-hover:text-white/70 transition-colors" style={{ color: 'rgba(255,255,255,0.45)' }}>
                              {(evt.details as Record<string, string>)?.title ||
                               (evt.details as Record<string, string>)?.reason ||
                               evt.event}
                            </p>
                            <p className="text-[9px]" style={{ color: 'rgba(255,255,255,0.12)' }}>{timeAgo(evt.timestamp)}</p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ) : (
                <p className="text-xs py-4 text-center" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune activité</p>
              )}
            </div>
          </div>

          {/* ═══ ROW 7 : Pipeline technique ═══════════════ */}
          {stats && (
            <div className="glass-card-static p-4">
              <h2 className="text-[10px] uppercase tracking-wider mb-3 font-semibold" style={{ color: 'rgba(255,255,255,0.25)' }}>Pipeline technique</h2>
              <div className="flex items-center gap-3 lg:gap-4 overflow-x-auto pb-1">
                {[
                  { label: 'Candidats', value: stats.candidates_total, sub: 'Ingestion', color: '#fbbf24', bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.15)' },
                  { label: 'Non classés', value: stats.candidates_unclustered, sub: 'En attente', color: '#f87171', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.15)' },
                  { label: 'Clusters', value: stats.clusters_active, sub: 'Groupement', color: '#facc15', bg: 'rgba(22,163,74,0.08)', border: 'rgba(22,163,74,0.15)' },
                  { label: 'Affaires', value: stats.affairs_active, sub: 'Promues', color: '#60a5fa', bg: 'rgba(37,99,235,0.08)', border: 'rgba(37,99,235,0.15)' },
                  { label: 'En veille', value: stats.affairs_stale, sub: 'Archivage', color: 'rgba(255,255,255,0.35)', bg: 'rgba(255,255,255,0.03)', border: 'rgba(255,255,255,0.06)' },
                ].map((step, i, arr) => (
                  <div key={i} className="flex items-center gap-3 flex-shrink-0">
                    <div className="w-9 h-9 rounded-full flex items-center justify-center" style={{ background: step.bg, border: `1px solid ${step.border}` }}>
                      <span className="text-xs font-bold" style={{ color: step.color }}>{step.value ?? 0}</span>
                    </div>
                    <div>
                      <p className="text-[10px] font-medium" style={{ color: 'rgba(255,255,255,0.45)' }}>{step.label}</p>
                      <p className="text-[9px]" style={{ color: 'rgba(255,255,255,0.18)' }}>{step.sub}</p>
                    </div>
                    {i < arr.length - 1 && (
                      <svg className="w-3.5 h-3.5" style={{ color: 'rgba(255,255,255,0.1)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
