'use client'

import { useEffect, useState } from 'react'
import {
  fetchSocialEvolution,
  fetchSocialHistory,
  type SocialEvolution,
  type AccountSnapshot,
} from '../../../lib/api'

// ── Couleurs plateformes (alignées sur la page social) ──
const PLAT: Record<string, { label: string; color: string }> = {
  instagram: { label: 'Instagram', color: '#e4405f' },
  facebook: { label: 'Facebook', color: '#1877f2' },
  tiktok: { label: 'TikTok', color: '#00f2ea' },
}

function fmt(n?: number | null): string {
  if (n === null || n === undefined) return '—'
  if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'k'
  return String(n)
}

function Delta({ value }: { value?: number | null }) {
  if (value === null || value === undefined) return <span className="text-white/25 text-[11px]">—</span>
  const up = value > 0
  const flat = value === 0
  const color = flat ? 'rgba(255,255,255,0.4)' : up ? '#34d399' : '#f87171'
  const arrow = flat ? '→' : up ? '▲' : '▼'
  return (
    <span className="text-[11px] font-semibold tabular-nums" style={{ color }}>
      {arrow} {fmt(Math.abs(value))}
    </span>
  )
}

/** Mini-courbe SVG d'engagement (cohérente avec le style custom du dashboard). */
function Sparkline({ data, color }: { data: AccountSnapshot[]; color: string }) {
  if (data.length < 2) {
    return <div className="h-12 flex items-center text-[10px] text-white/25">Historique en construction…</div>
  }
  const vals = data.map(d => d.engagement)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = max - min || 1
  const W = 100
  const H = 40
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * W
    const y = H - ((d.engagement - min) / span) * H
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const linePath = `M ${pts.join(' L ')}`
  const areaPath = `${linePath} L ${W},${H} L 0,${H} Z`
  const gid = `grad-${color.replace('#', '')}`
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="w-full h-12">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gid})`} />
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export function SocialEvolutionPanel({ days = 30, end = null }: { days?: number; end?: string | null }) {
  const [evo, setEvo] = useState<SocialEvolution | null>(null)
  const [history, setHistory] = useState<Record<string, AccountSnapshot[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    // Les courbes suivent l'horizon et la période choisis.
    Promise.all([fetchSocialEvolution(), fetchSocialHistory(undefined, days, end)])
      .then(([e, h]) => {
        if (!alive) return
        setEvo(e)
        setHistory(h.series || {})
      })
      .catch(() => { if (alive) setError(true) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [days, end])

  if (loading) {
    return (
      <div className="rounded-2xl p-5 animate-pulse" style={{ background: 'rgba(255,255,255,0.03)' }}>
        <div className="h-4 w-40 rounded bg-white/10 mb-4" />
        <div className="h-24 rounded bg-white/5" />
      </div>
    )
  }

  if (error || !evo) {
    return (
      <div className="rounded-2xl p-5 text-[12px] text-white/40" style={{ background: 'rgba(255,255,255,0.03)' }}>
        Évolution indisponible pour le moment.
      </div>
    )
  }

  const platforms = Object.keys(PLAT).filter(p => evo.platforms[p]?.available || (history[p]?.length ?? 0) > 0)

  if (platforms.length === 0) {
    return (
      <div className="rounded-2xl p-5" style={{ background: 'rgba(255,255,255,0.03)' }}>
        <h3 className="text-sm font-semibold text-white/80 mb-1">Évolution</h3>
        <p className="text-[12px] text-white/40">
          Aucun snapshot encore enregistré. Le premier instantané sera capturé ce soir —
          la courbe se construira jour après jour.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl p-5" style={{ background: 'rgba(255,255,255,0.03)' }}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white/80">Évolution · 30 jours</h3>
        <span className="text-[10px] text-white/30">engagement = likes + commentaires + partages</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {platforms.map(p => {
          const meta = PLAT[p]
          const e = evo.platforms[p] || { available: false }
          const series = history[p] || []
          return (
            <div key={p} className="rounded-xl p-3.5" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[12px] font-semibold" style={{ color: meta.color }}>{meta.label}</span>
                <span className="text-[10px] text-white/30 tabular-nums">{e.posts_count ?? 0} posts</span>
              </div>

              <div className="flex items-baseline gap-2 mb-1">
                <span className="text-xl font-bold text-white tabular-nums">{fmt(e.engagement)}</span>
                <Delta value={e.delta_engagement_7d} />
                <span className="text-[10px] text-white/30">7j</span>
              </div>

              <Sparkline data={series} color={meta.color} />

              <div className="flex items-center justify-between mt-2 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                <span className="text-[11px] text-white/40">
                  Abonnés <span className="text-white/70 font-medium tabular-nums">{fmt(e.followers)}</span>
                </span>
                <Delta value={e.delta_followers_7d} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default SocialEvolutionPanel
