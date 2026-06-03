'use client'

import { useEffect, useState } from 'react'
import { fetchDecisionInsights, type DecisionInsights as Insights, type InsightPost } from '../../../lib/api'

const PLAT_COLOR: Record<string, string> = {
  instagram: '#e4405f', facebook: '#1877f2', tiktok: '#00f2ea',
}

function fmt(n?: number | null): string {
  if (n === null || n === undefined) return '—'
  if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'k'
  return String(Math.round(n))
}

function sentimentColor(global?: string): string {
  const g = (global || '').toLowerCase()
  if (g.includes('posit')) return '#34d399'
  if (g.includes('nég') || g.includes('neg')) return '#f87171'
  if (g.includes('mitig')) return '#fbbf24'
  return 'rgba(255,255,255,0.5)'
}

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
function mediaSrc(url: string): string {
  if (!url) return ''
  return url.startsWith('http') ? url : `${BACKEND}${url}`
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl p-4 ${className}`} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
      {children}
    </div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] uppercase tracking-[0.14em] font-semibold mb-2.5" style={{ color: 'rgba(255,255,255,0.4)' }}>{children}</div>
}

/** Carte « Post le plus vu de la période ». */
function TopPostCard({ post }: { post: InsightPost }) {
  const src = mediaSrc(post.media_url)
  return (
    <Card>
      <Label>🏆 Post le plus vu</Label>
      <div className="flex gap-3">
        {src ? (
          <img src={src} alt="" className="w-20 h-20 rounded-lg object-cover shrink-0" style={{ border: '1px solid rgba(255,255,255,0.08)' }} />
        ) : (
          <div className="w-20 h-20 rounded-lg shrink-0 flex items-center justify-center text-2xl" style={{ background: 'rgba(255,255,255,0.04)' }}>📄</div>
        )}
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-white leading-snug line-clamp-2">{post.title}</div>
          <div className="flex items-center gap-2 mt-1.5">
            {post.platform && (
              <span className="text-[10px] font-semibold" style={{ color: PLAT_COLOR[post.platform] || '#fff' }}>
                {post.platform}
              </span>
            )}
            <span className="text-[10px] text-white/30">· {post.campaign_name}</span>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-3">
        {[['Vues', post.stats.views], ['Likes', post.stats.likes], ['Comm.', post.stats.comments]].map(([l, v]) => (
          <div key={l as string} className="rounded-lg py-2 text-center" style={{ background: 'rgba(255,255,255,0.02)' }}>
            <div className="text-base font-bold text-white tabular-nums">{fmt(v as number)}</div>
            <div className="text-[9px] text-white/35">{l}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

/** Carte « Ce qui marche » (analyse IA). */
function WhatWorksCard({ ww }: { ww: NonNullable<Insights['what_works']> }) {
  const items: [string, string | undefined][] = [
    ['Format', ww.best_format],
    ['Plateforme', ww.best_platform],
    ['Jour', ww.best_day],
    ['Heure', ww.best_time],
  ]
  return (
    <Card>
      <Label>✨ Ce qui marche</Label>
      <div className="grid grid-cols-2 gap-2.5">
        {items.map(([l, v]) => (
          <div key={l}>
            <div className="text-[10px] text-white/35">{l}</div>
            <div className="text-sm font-semibold capitalize" style={{ color: v ? '#5FD0E0' : 'rgba(255,255,255,0.25)' }}>
              {v || '—'}
            </div>
          </div>
        ))}
      </div>
      {ww.engagement_rate != null && (
        <div className="mt-3 pt-2.5 text-[11px] text-white/40" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          Taux d'engagement <span className="text-white/70 font-semibold">{(ww.engagement_rate * 100).toFixed(1)}%</span>
        </div>
      )}
      {ww.from_campaign && (
        <div className="text-[9px] text-white/25 mt-1">d'après l'analyse de « {ww.from_campaign} »</div>
      )}
    </Card>
  )
}

/** Carte « Sentiment + recommandations IA ». */
function SentimentCard({ sentiment, recommendations, summary }: Pick<Insights, 'sentiment' | 'recommendations' | 'summary'>) {
  const color = sentimentColor(sentiment?.global)
  return (
    <Card>
      <Label>🧭 Sentiment & recommandations</Label>
      {sentiment ? (
        <div className="flex items-center gap-2 mb-2.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
          <span className="text-sm font-semibold capitalize" style={{ color }}>{sentiment.global}</span>
          {sentiment.score != null && (
            <span className="text-[11px] text-white/40 tabular-nums">({Math.round(sentiment.score * 100)}%)</span>
          )}
        </div>
      ) : (
        <div className="text-[11px] text-white/30 mb-2.5">Pas encore d'analyse IA — lance-la sur une campagne.</div>
      )}
      {summary && <p className="text-[11px] text-white/50 leading-relaxed mb-2.5">{summary}</p>}
      {recommendations.length > 0 && (
        <ul className="space-y-1.5">
          {recommendations.map((r, i) => (
            <li key={i} className="flex gap-2 text-[11px] text-white/70 leading-snug">
              <span className="text-white/30">{i + 1}.</span>{r}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

/** Carte « Top 3 + commentaires ». */
function TopThreeCard({ posts }: { posts: InsightPost[] }) {
  return (
    <Card>
      <Label>📊 Top 3 & réactions</Label>
      <div className="space-y-2.5">
        {posts.map((p, i) => (
          <div key={p._id} className="flex items-start gap-2.5">
            <span className="text-sm font-bold text-white/25 tabular-nums w-4 shrink-0">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="text-[12px] font-medium text-white/90 truncate">{p.title}</div>
              <div className="text-[10px] text-white/35 tabular-nums">
                {fmt(p.stats.views)} vues · {fmt(p.engagement)} interactions
              </div>
              {p.top_comments[0] && (
                <div className="text-[10px] text-white/45 italic truncate mt-0.5">« {p.top_comments[0].text} »</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

export function DecisionInsights({ days = 7, compact = false }: { days?: number; compact?: boolean }) {
  const [data, setData] = useState<Insights | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let alive = true
    fetchDecisionInsights(days)
      .then(d => { if (alive) { setData(d); setState('ready') } })
      .catch(() => { if (alive) setState('error') })
    return () => { alive = false }
  }, [days])

  if (state === 'loading') {
    return <div className="rounded-2xl p-5 animate-pulse h-32" style={{ background: 'rgba(255,255,255,0.03)' }} />
  }
  if (state === 'error' || !data) {
    return <div className="rounded-2xl p-4 text-[12px] text-white/40" style={{ background: 'rgba(255,255,255,0.03)' }}>Insights indisponibles.</div>
  }

  if (!data.top_post) {
    return (
      <Card>
        <Label>Outil de décision</Label>
        <p className="text-[12px] text-white/40">Aucun post avec des statistiques sur {data.days >= 365 ? 'les 12 derniers mois' : `les ${data.days} derniers jours`}. Publie et lance un scrape pour alimenter ces cartes.</p>
      </Card>
    )
  }

  // Mode compact (barre insights en haut de /social) : top post + ce qui marche + sentiment.
  if (compact) {
    return (
      <div className="grid gap-3 md:grid-cols-3">
        {data.top_post && <TopPostCard post={data.top_post} />}
        {data.what_works && <WhatWorksCard ww={data.what_works} />}
        <SentimentCard sentiment={data.sentiment} recommendations={data.recommendations} summary={data.summary} />
      </div>
    )
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {data.top_post && <TopPostCard post={data.top_post} />}
      {data.what_works && <WhatWorksCard ww={data.what_works} />}
      <SentimentCard sentiment={data.sentiment} recommendations={data.recommendations} summary={data.summary} />
      {data.top_posts.length > 0 && <TopThreeCard posts={data.top_posts} />}
    </div>
  )
}

export default DecisionInsights
