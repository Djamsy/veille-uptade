// Bilan hebdomadaire « réseaux sociaux » — export PNG haute résolution.
// Rendu sur canvas natif (aucune dépendance). Format A4 portrait.
// Combine : KPI héro + tendances, évolution par plateforme (sparklines),
// post de la semaine, top 3, sentiment + recommandations, trafic web.

import type {
  SocialEvolution, WebTrafficPoint, DecisionInsights, AccountSnapshot,
} from './api'

export interface WeeklyReportData {
  web: WebTrafficPoint | null
  webPrev?: WebTrafficPoint | null      // point précédent (pour tendance trafic)
  evolution: SocialEvolution | null
  insights: DecisionInsights | null
  history?: Record<string, AccountSnapshot[]>  // séries 30j par plateforme (sparklines)
}

const PLATFORMS = ['instagram', 'facebook', 'tiktok'] as const
const PLAT_COLOR: Record<string, string> = {
  instagram: '#e4405f', facebook: '#1877f2', tiktok: '#25F4EE',
}
const PLAT_LABEL: Record<string, string> = {
  instagram: 'Instagram', facebook: 'Facebook', tiktok: 'TikTok',
}

// Palette
const INK = '#0a1822'
const INK2 = '#0f2230'
const ACCENT = '#5FD0E0'
const WHITE = '#ffffff'
const MUTED = 'rgba(255,255,255,0.45)'
const MUTED2 = 'rgba(255,255,255,0.28)'
const GREEN = '#34d399'
const RED = '#f87171'
const AMBER = '#fbbf24'

function fmt(n?: number | null): string {
  if (n === null || n === undefined) return '—'
  const a = Math.abs(n)
  if (a >= 1_000_000) return (n / 1_000_000).toFixed(1).replace('.0', '') + 'M'
  if (a >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'k'
  return String(Math.round(n))
}

function frDate(d: Date): string {
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}
function frDateShort(d: Date): string {
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

function sentimentColor(global?: string): string {
  const g = (global || '').toLowerCase()
  if (g.includes('posit')) return GREEN
  if (g.includes('nég') || g.includes('neg')) return RED
  if (g.includes('mitig')) return AMBER
  return MUTED
}

function pct(curr?: number | null, prev?: number | null): number | null {
  if (curr == null || prev == null || prev === 0) return null
  return ((curr - prev) / prev) * 100
}

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
function mediaSrc(url: string): string {
  if (!url) return ''
  return url.startsWith('http') ? url : `${BACKEND}${url}`
}

// Chargeur d'image injectable (navigateur par défaut ; un rendu Node peut fournir le sien).
type ImageLoader = (url: string) => Promise<CanvasImageSource | null>

// Charge une image (CORS) ; résout null si échec, pour ne jamais bloquer l'export.
const browserImageLoader: ImageLoader = (url) =>
  new Promise(resolve => {
    if (!url) return resolve(null)
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)
    img.src = url
  })

// ── Helpers de dessin ──
function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function card(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  roundRect(ctx, x, y, w, h, 16)
  ctx.fillStyle = 'rgba(255,255,255,0.04)'
  ctx.fill()
  ctx.strokeStyle = 'rgba(255,255,255,0.07)'
  ctx.lineWidth = 1
  ctx.stroke()
}

function trendBadge(ctx: CanvasRenderingContext2D, x: number, y: number, p: number | null) {
  if (p === null) return
  const up = p > 0.5, down = p < -0.5
  const color = up ? GREEN : down ? RED : MUTED
  const arrow = up ? '▲' : down ? '▼' : '→'
  ctx.fillStyle = color
  ctx.font = '600 22px Inter, system-ui, sans-serif'
  ctx.fillText(`${arrow} ${Math.abs(p).toFixed(0)}%`, x, y)
}

function sparkline(ctx: CanvasRenderingContext2D, pts: number[], x: number, y: number, w: number, h: number, color: string) {
  if (pts.length < 2) {
    ctx.fillStyle = MUTED2
    ctx.font = '400 16px Inter, system-ui, sans-serif'
    ctx.fillText('historique en cours…', x, y + h / 2)
    return
  }
  const min = Math.min(...pts), max = Math.max(...pts)
  const span = max - min || 1
  const step = w / (pts.length - 1)
  const xy = pts.map((v, i) => [x + i * step, y + h - ((v - min) / span) * h] as const)

  // aire
  const grad = ctx.createLinearGradient(0, y, 0, y + h)
  grad.addColorStop(0, color + '44')
  grad.addColorStop(1, color + '00')
  ctx.beginPath()
  ctx.moveTo(xy[0][0], xy[0][1])
  xy.forEach(p => ctx.lineTo(p[0], p[1]))
  ctx.lineTo(x + w, y + h); ctx.lineTo(x, y + h); ctx.closePath()
  ctx.fillStyle = grad; ctx.fill()
  // ligne
  ctx.beginPath()
  ctx.moveTo(xy[0][0], xy[0][1])
  xy.forEach(p => ctx.lineTo(p[0], p[1]))
  ctx.strokeStyle = color; ctx.lineWidth = 2.5
  ctx.lineJoin = 'round'; ctx.lineCap = 'round'
  ctx.stroke()
}

// Camembert/donut : segments = [valeur, couleur]. Dessiné centré en (cx, cy).
function donut(ctx: CanvasRenderingContext2D, segs: [number, string][], cx: number, cy: number, rOut: number, rIn: number) {
  const total = segs.reduce((s, [v]) => s + v, 0)
  if (total <= 0) {
    ctx.beginPath(); ctx.arc(cx, cy, rOut, 0, Math.PI * 2); ctx.arc(cx, cy, rIn, 0, Math.PI * 2, true)
    ctx.fillStyle = 'rgba(255,255,255,0.05)'; ctx.fill('evenodd')
    return
  }
  let a = -Math.PI / 2
  segs.forEach(([v, color]) => {
    const slice = (v / total) * Math.PI * 2
    ctx.beginPath()
    ctx.arc(cx, cy, rOut, a, a + slice)
    ctx.arc(cx, cy, rIn, a + slice, a, true)
    ctx.closePath()
    ctx.fillStyle = color; ctx.fill()
    a += slice
  })
}

export const REPORT_W = 1240
export const REPORT_H = 1754

/**
 * Dessine le bilan sur un contexte 2D fourni (logique pure, réutilisable
 * navigateur + Node). Le contexte doit déjà être à l'échelle voulue.
 */
export async function drawWeeklyReport(
  ctx: CanvasRenderingContext2D,
  data: WeeklyReportData,
  loadImage: ImageLoader = browserImageLoader,
): Promise<number> {
  const W = REPORT_W, H = REPORT_H

  const now = new Date()
  const weekAgo = new Date(now.getTime() - 7 * 86400000)
  const ins = data.insights
  const evo = data.evolution?.platforms || {}

  // ── Fond ──
  const bg = ctx.createLinearGradient(0, 0, 0, H)
  bg.addColorStop(0, INK2); bg.addColorStop(0.35, INK); bg.addColorStop(1, '#07141c')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, W, H)

  const PAD = 56
  const CW = W - PAD * 2

  // ── En-tête ──
  const headH = 150
  const hg = ctx.createLinearGradient(0, 0, W, headH)
  hg.addColorStop(0, 'rgba(95,208,224,0.16)'); hg.addColorStop(1, 'rgba(95,208,224,0)')
  ctx.fillStyle = hg
  ctx.fillRect(0, 0, W, headH)
  ctx.fillStyle = ACCENT
  ctx.fillRect(0, 0, 6, headH)

  ctx.fillStyle = ACCENT
  ctx.font = '700 14px Inter, system-ui, sans-serif'
  ctx.fillText('OBSERVATOIRE · BILAN HEBDOMADAIRE', PAD, 52)
  ctx.fillStyle = WHITE
  ctx.font = '700 34px Georgia, serif'
  ctx.fillText('Réseaux sociaux & audience', PAD, 96)
  ctx.fillStyle = MUTED
  ctx.font = '400 17px Inter, system-ui, sans-serif'
  ctx.fillText(`Conseil Départemental de la Guadeloupe · ${frDateShort(weekAgo)} → ${frDateShort(now)}`, PAD, 126)

  let y = headH + 28

  // ── Faits marquants (auto-générés à partir des plus gros mouvements) ──
  const highlights: string[] = []
  {
    // meilleure progression d'engagement par plateforme
    const movers = PLATFORMS
      .map(p => ({ p, d: evo[p]?.delta_engagement_7d ?? null }))
      .filter(m => m.d != null) as { p: string; d: number }[]
    movers.sort((a, b) => b.d - a.d)
    if (movers[0] && movers[0].d > 0)
      highlights.push(`${PLAT_LABEL[movers[0].p]} en tête : +${fmt(movers[0].d)} d'engagement sur 7 jours`)
    // trafic web
    const wp = pct(data.web?.sessions, data.webPrev?.sessions)
    if (wp != null && Math.abs(wp) >= 3)
      highlights.push(`Trafic web ${wp > 0 ? 'en hausse' : 'en baisse'} de ${Math.abs(wp).toFixed(0)}% vs semaine passée`)
    // post phare
    if (data.insights?.top_post)
      highlights.push(`Post phare : ${fmt(data.insights.top_post.stats.views)} vues sur ${PLAT_LABEL[data.insights.top_post.platform] || data.insights.top_post.platform}`)
  }
  if (highlights.length) {
    const fmH = 56
    roundRect(ctx, PAD, y, CW, fmH, 12)
    ctx.fillStyle = 'rgba(95,208,224,0.07)'; ctx.fill()
    ctx.strokeStyle = 'rgba(95,208,224,0.18)'; ctx.lineWidth = 1; ctx.stroke()
    ctx.fillStyle = ACCENT
    ctx.font = '700 12px Inter, system-ui, sans-serif'
    ctx.fillText('★ FAITS MARQUANTS', PAD + 18, y + 23)
    ctx.fillStyle = 'rgba(255,255,255,0.82)'
    ctx.font = '400 14px Inter, system-ui, sans-serif'
    ctx.fillText(highlights.join('   ·   '), PAD + 18, y + 42)
    y += fmH + 28
  }

  // ── KPI héros (3) ──
  const totalEngagement = ins?.totals?.engagement ?? Object.values(evo).reduce((s, p) => s + (p.engagement || 0), 0)
  const totalFollowers = PLATFORMS.reduce((s, p) => s + (evo[p]?.followers || 0), 0)
  const sumDelta7 = PLATFORMS.reduce((s, p) => s + (evo[p]?.delta_engagement_7d || 0), 0)
  const engagePrev = totalEngagement - sumDelta7
  const folDelta7 = PLATFORMS.reduce((s, p) => s + (evo[p]?.delta_followers_7d || 0), 0)
  const folPrev = totalFollowers - folDelta7
  const webNow = data.web?.sessions
  const webPrev = data.webPrev?.sessions

  const heroes: [string, string, number | null][] = [
    ['Engagement total', fmt(totalEngagement), pct(totalEngagement, engagePrev || null)],
    ['Abonnés cumulés', fmt(totalFollowers), pct(totalFollowers, folPrev || null)],
    ['Sessions web', fmt(webNow), pct(webNow, webPrev)],
  ]
  const heroW = (CW - 2 * 16) / 3
  const heroH = 124
  heroes.forEach(([label, val, p], i) => {
    const x = PAD + i * (heroW + 16)
    card(ctx, x, y, heroW, heroH)
    ctx.fillStyle = MUTED
    ctx.font = '600 14px Inter, system-ui, sans-serif'
    ctx.fillText(label.toUpperCase(), x + 20, y + 32)
    ctx.fillStyle = WHITE
    ctx.font = '700 44px Inter, system-ui, sans-serif'
    ctx.fillText(val, x + 20, y + 82)
    trendBadge(ctx, x + 20, y + 110, p)
    ctx.fillStyle = MUTED2
    ctx.font = '400 13px Inter, system-ui, sans-serif'
    if (p !== null) ctx.fillText('vs 7j', x + 20 + ctx.measureText(`${p > 0 ? '▲' : p < 0 ? '▼' : '→'} ${Math.abs(p).toFixed(0)}%  `).width, y + 110)
  })
  y += heroH + 36

  // ── Section : par plateforme ──
  const sectionTitle = (label: string) => {
    ctx.fillStyle = MUTED
    ctx.font = '700 15px Inter, system-ui, sans-serif'
    ctx.fillText(label.toUpperCase(), PAD, y)
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(PAD, y + 14); ctx.lineTo(W - PAD, y + 14); ctx.stroke()
    y += 40
  }

  sectionTitle('Performance par plateforme')
  const pcW = (CW - 2 * 16) / 3
  const pcH = 190
  PLATFORMS.forEach((p, i) => {
    const e = evo[p]
    const x = PAD + i * (pcW + 16)
    card(ctx, x, y, pcW, pcH)
    const color = PLAT_COLOR[p]
    // bandeau couleur
    roundRect(ctx, x, y, pcW, 5, 2); ctx.fillStyle = color; ctx.fill()

    ctx.fillStyle = color
    ctx.font = '700 18px Inter, system-ui, sans-serif'
    ctx.fillText(PLAT_LABEL[p], x + 18, y + 38)

    ctx.fillStyle = WHITE
    ctx.font = '700 32px Inter, system-ui, sans-serif'
    ctx.fillText(fmt(e?.engagement), x + 18, y + 76)
    ctx.fillStyle = MUTED2
    ctx.font = '400 13px Inter, system-ui, sans-serif'
    ctx.fillText('engagement', x + 18, y + 95)
    trendBadge(ctx, x + 18, y + 122, e?.delta_engagement_7d != null && e?.engagement != null
      ? pct(e.engagement, e.engagement - e.delta_engagement_7d) : null)

    // sparkline 30j
    const serie = (data.history?.[p] || []).map(s => s.engagement)
    sparkline(ctx, serie, x + 18, y + 134, pcW - 36, 30, color)

    // followers
    ctx.fillStyle = MUTED
    ctx.font = '500 14px Inter, system-ui, sans-serif'
    ctx.fillText(`${fmt(e?.followers)} abonnés`, x + 18, y + pcH - 14)
  })
  y += pcH + 36

  // ── Post de la semaine + Top 3 (deux colonnes) ──
  sectionTitle('Le contenu qui a marqué la semaine')
  const colGap = 16
  const leftW = CW * 0.52, rightW = CW - leftW - colGap
  const blockH = 230
  const leftX = PAD, rightX = PAD + leftW + colGap

  // Carte « post de la semaine »
  card(ctx, leftX, y, leftW, blockH)
  ctx.fillStyle = AMBER
  ctx.font = '700 13px Inter, system-ui, sans-serif'
  ctx.fillText('🏆 POST DE LA SEMAINE', leftX + 18, y + 30)
  const tp = ins?.top_post
  const thumb = tp ? await loadImage(mediaSrc(tp.media_url)) : null
  if (tp) {
    const imgS = 96
    if (thumb) {
      ctx.save(); roundRect(ctx, leftX + 18, y + 46, imgS, imgS, 10); ctx.clip()
      ctx.drawImage(thumb, leftX + 18, y + 46, imgS, imgS); ctx.restore()
    } else {
      roundRect(ctx, leftX + 18, y + 46, imgS, imgS, 10); ctx.fillStyle = 'rgba(255,255,255,0.05)'; ctx.fill()
      ctx.fillStyle = MUTED2; ctx.font = '32px serif'; ctx.fillText('📄', leftX + 18 + 30, y + 46 + 60)
    }
    const tx = leftX + 18 + imgS + 16
    const tw = leftW - (imgS + 52)
    ctx.fillStyle = WHITE
    ctx.font = '600 18px Inter, system-ui, sans-serif'
    // titre sur 2 lignes max
    wrapText(ctx, tp.title, tx, y + 70, tw, 24, 2)
    if (tp.platform) {
      ctx.fillStyle = PLAT_COLOR[tp.platform] || WHITE
      ctx.font = '600 13px Inter, system-ui, sans-serif'
      ctx.fillText(PLAT_LABEL[tp.platform] || tp.platform, tx, y + 132)
    }
    // stats en ligne
    const stats: [string, number][] = [['Vues', tp.stats.views], ['Likes', tp.stats.likes], ['Comm.', tp.stats.comments]]
    const sw = (leftW - 36) / 3
    stats.forEach(([l, v], i) => {
      const sx = leftX + 18 + i * sw
      ctx.fillStyle = WHITE
      ctx.font = '700 24px Inter, system-ui, sans-serif'
      ctx.fillText(fmt(v), sx, y + blockH - 30)
      ctx.fillStyle = MUTED2
      ctx.font = '400 12px Inter, system-ui, sans-serif'
      ctx.fillText(l, sx, y + blockH - 12)
    })
  } else {
    ctx.fillStyle = MUTED
    ctx.font = '400 15px Inter, system-ui, sans-serif'
    ctx.fillText('Pas encore de posts avec statistiques.', leftX + 18, y + 80)
  }

  // Carte « Top 3 »
  card(ctx, rightX, y, rightW, blockH)
  ctx.fillStyle = ACCENT
  ctx.font = '700 13px Inter, system-ui, sans-serif'
  ctx.fillText('📊 TOP 3 PUBLICATIONS', rightX + 18, y + 30)
  const top3 = ins?.top_posts || []
  const maxV = Math.max(1, ...top3.map(p => p.stats.views))
  if (top3.length) {
    top3.forEach((p, i) => {
      const ry = y + 56 + i * 52
      ctx.fillStyle = MUTED2
      ctx.font = '700 18px Inter, system-ui, sans-serif'
      ctx.fillText(String(i + 1), rightX + 18, ry + 16)
      ctx.fillStyle = WHITE
      ctx.font = '500 14px Inter, system-ui, sans-serif'
      const title = p.title.length > 40 ? p.title.slice(0, 38) + '…' : p.title
      ctx.fillText(title, rightX + 42, ry + 8)
      // barre proportionnelle
      const bw = (rightW - 60) * (p.stats.views / maxV)
      roundRect(ctx, rightX + 42, ry + 18, rightW - 60, 6, 3); ctx.fillStyle = 'rgba(255,255,255,0.06)'; ctx.fill()
      roundRect(ctx, rightX + 42, ry + 18, Math.max(bw, 4), 6, 3); ctx.fillStyle = ACCENT; ctx.fill()
      ctx.fillStyle = MUTED
      ctx.font = '400 12px Inter, system-ui, sans-serif'
      ctx.fillText(`${fmt(p.stats.views)} vues · ${fmt(p.engagement)} interactions`, rightX + 42, ry + 38)
    })
  } else {
    ctx.fillStyle = MUTED
    ctx.font = '400 15px Inter, system-ui, sans-serif'
    ctx.fillText('Aucune donnée.', rightX + 18, y + 70)
  }
  y += blockH + 36

  // ── Répartition de l'engagement + perception (deux colonnes) ──
  sectionTitle("Répartition de l'engagement & perception")
  const splitH = 210
  const dW = CW * 0.42, sW = CW - dW - 16
  const dX = PAD, sX = PAD + dW + 16

  // Carte donut : part d'engagement par plateforme
  card(ctx, dX, y, dW, splitH)
  ctx.fillStyle = MUTED
  ctx.font = '700 12px Inter, system-ui, sans-serif'
  ctx.fillText("PART D'ENGAGEMENT", dX + 18, y + 28)
  const shares = PLATFORMS.map(p => [evo[p]?.engagement || 0, PLAT_COLOR[p]] as [number, string])
  const shareTotal = shares.reduce((a, [v]) => a + v, 0)
  const cx = dX + 78, cy = y + splitH / 2 + 16
  donut(ctx, shares, cx, cy, 56, 33)
  // total au centre
  ctx.textAlign = 'center'
  ctx.fillStyle = WHITE
  ctx.font = '700 20px Inter, system-ui, sans-serif'
  ctx.fillText(fmt(shareTotal), cx, cy + 2)
  ctx.fillStyle = MUTED2
  ctx.font = '400 10px Inter, system-ui, sans-serif'
  ctx.fillText('TOTAL', cx, cy + 18)
  ctx.textAlign = 'left'
  // légende
  PLATFORMS.forEach((p, i) => {
    const ly = y + 70 + i * 36
    const lx = dX + 160
    ctx.fillStyle = PLAT_COLOR[p]
    roundRect(ctx, lx, ly - 9, 11, 11, 3); ctx.fill()
    ctx.fillStyle = WHITE
    ctx.font = '600 14px Inter, system-ui, sans-serif'
    ctx.fillText(PLAT_LABEL[p], lx + 20, ly)
    const share = shareTotal ? Math.round(((evo[p]?.engagement || 0) / shareTotal) * 100) : 0
    ctx.fillStyle = MUTED
    ctx.font = '400 13px Inter, system-ui, sans-serif'
    ctx.fillText(`${share}%  ·  ${fmt(evo[p]?.engagement)}`, lx + 20, ly + 17)
  })

  // Carte perception : sentiment + score + thèmes
  card(ctx, sX, y, sW, splitH)
  const s = ins?.sentiment
  const sc = sentimentColor(s?.global)
  ctx.fillStyle = MUTED
  ctx.font = '700 12px Inter, system-ui, sans-serif'
  ctx.fillText('PERCEPTION DE L\'AUDIENCE', sX + 18, y + 28)
  ctx.fillStyle = sc
  ctx.beginPath(); ctx.arc(sX + 26, y + 58, 8, 0, Math.PI * 2); ctx.fill()
  ctx.fillStyle = WHITE
  ctx.font = '700 22px Inter, system-ui, sans-serif'
  const sLabel = s?.global ? s.global[0].toUpperCase() + s.global.slice(1) : 'Non analysé'
  ctx.fillText(sLabel, sX + 44, y + 65)
  // barre de score
  if (s?.score != null) {
    const barX = sX + 18, barW = sW - 36, barY = y + 86
    roundRect(ctx, barX, barY, barW, 8, 4); ctx.fillStyle = 'rgba(255,255,255,0.08)'; ctx.fill()
    roundRect(ctx, barX, barY, Math.max(barW * Math.min(Math.max(s.score, 0), 1), 6), 8, 4); ctx.fillStyle = sc; ctx.fill()
    ctx.fillStyle = MUTED
    ctx.font = '600 13px Inter, system-ui, sans-serif'
    ctx.fillText(`Score ${Math.round(s.score * 100)}%`, barX, barY + 28)
  }
  // thèmes / mots-clés en chips
  const themes = (s?.themes || []).slice(0, 6)
  if (themes.length) {
    let chx = sX + 18, chy = y + 128
    ctx.font = '600 13px Inter, system-ui, sans-serif'
    themes.forEach(t => {
      const tw = ctx.measureText(t).width + 26
      if (chx + tw > sX + sW - 18) { chx = sX + 18; chy += 34 }
      roundRect(ctx, chx, chy, tw, 26, 13)
      ctx.fillStyle = 'rgba(95,208,224,0.12)'; ctx.fill()
      ctx.strokeStyle = 'rgba(95,208,224,0.3)'; ctx.lineWidth = 1; ctx.stroke()
      ctx.fillStyle = ACCENT
      ctx.fillText(t, chx + 13, chy + 17)
      chx += tw + 8
    })
  }
  // résumé
  if (ins?.summary) {
    ctx.fillStyle = 'rgba(255,255,255,0.55)'
    ctx.font = '400 13px Inter, system-ui, sans-serif'
    wrapText(ctx, ins.summary, sX + 18, themes.length ? y + 188 : y + 140, sW - 36, 20, themes.length ? 1 : 3)
  }
  y += splitH + 36

  // ── Recommandations IA (pleine largeur) ──
  sectionTitle('Recommandations IA')
  const recos = (ins?.recommendations || []).slice(0, 3)
  const recoH = recos.length ? 30 + recos.length * 56 : 80
  card(ctx, PAD, y, CW, recoH)
  if (recos.length) {
    recos.forEach((r, i) => {
      const ry = y + 22 + i * 56
      // pastille numérotée
      ctx.beginPath(); ctx.arc(PAD + 36, ry + 14, 15, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(95,208,224,0.14)'; ctx.fill()
      ctx.fillStyle = ACCENT
      ctx.font = '700 15px Inter, system-ui, sans-serif'
      ctx.textAlign = 'center'; ctx.fillText(String(i + 1), PAD + 36, ry + 19); ctx.textAlign = 'left'
      ctx.fillStyle = 'rgba(255,255,255,0.85)'
      ctx.font = '400 15px Inter, system-ui, sans-serif'
      wrapText(ctx, r, PAD + 66, ry + 12, CW - 100, 21, 2)
      if (i < recos.length - 1) {
        ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(PAD + 20, ry + 44); ctx.lineTo(W - PAD - 20, ry + 44); ctx.stroke()
      }
    })
  } else {
    ctx.fillStyle = MUTED
    ctx.font = '400 15px Inter, system-ui, sans-serif'
    ctx.fillText('Lance une analyse IA sur une campagne pour obtenir des recommandations.', PAD + 24, y + 46)
  }
  y += recoH + 36

  // ── Trafic web ──
  sectionTitle('Trafic du site web')
  const webCells: [string, string, number | null][] = [
    ['Sessions', fmt(data.web?.sessions), pct(data.web?.sessions, data.webPrev?.sessions)],
    ['Pages vues', fmt(data.web?.pageviews), pct(data.web?.pageviews, data.webPrev?.pageviews)],
    ['Utilisateurs', fmt(data.web?.users), pct(data.web?.users, data.webPrev?.users)],
    ['Nouveaux', fmt(data.web?.new_users), pct(data.web?.new_users, data.webPrev?.new_users)],
    ['Durée moy.', data.web?.avg_session_duration != null ? `${Math.round(data.web.avg_session_duration)}s` : '—', null],
    ['Rebond', data.web?.bounce_rate != null ? `${data.web.bounce_rate}%` : '—', null],
  ]
  const wcW = (CW - 5 * 12) / 6
  const wcH = 96
  webCells.forEach(([label, val, p], i) => {
    const x = PAD + i * (wcW + 12)
    card(ctx, x, y, wcW, wcH)
    ctx.fillStyle = MUTED2
    ctx.font = '400 12px Inter, system-ui, sans-serif'
    ctx.fillText(label, x + 12, y + 26)
    ctx.fillStyle = WHITE
    ctx.font = '700 22px Inter, system-ui, sans-serif'
    ctx.fillText(val, x + 12, y + 56)
    if (p !== null) {
      ctx.fillStyle = p > 0.5 ? GREEN : p < -0.5 ? RED : MUTED
      ctx.font = '600 12px Inter, system-ui, sans-serif'
      ctx.fillText(`${p > 0 ? '▲' : p < 0 ? '▼' : '→'} ${Math.abs(p).toFixed(0)}%`, x + 12, y + 78)
    }
  })
  y += wcH + 30

  // ── Pied de page ──
  ctx.strokeStyle = 'rgba(255,255,255,0.07)'; ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - PAD, y); ctx.stroke()
  ctx.fillStyle = MUTED2
  ctx.font = '400 13px Inter, system-ui, sans-serif'
  ctx.fillText(`Généré le ${frDate(now)} · Observatoire interne — données ${ins?.days ?? 7} derniers jours`, PAD, y + 26)

  // Hauteur réellement occupée par le contenu (pour rogner le vide en bas).
  return Math.min(H, y + 44)
}

/** Dessine le bilan sur un canvas hors-écran et renvoie le PNG en Blob.
 *  Rendu haute résolution (scale 3) et rognage du vide en bas pour une
 *  meilleure lisibilité, notamment dans l'aperçu Telegram. */
export async function renderWeeklyReportBlob(data: WeeklyReportData): Promise<Blob | null> {
  const scale = 3
  // 1) Dessin pleine page pour connaître la hauteur réelle du contenu.
  const full = document.createElement('canvas')
  full.width = REPORT_W * scale
  full.height = REPORT_H * scale
  const fctx = full.getContext('2d')!
  fctx.scale(scale, scale)
  const contentH = await drawWeeklyReport(fctx, data)

  // 2) Canvas final rogné à la hauteur du contenu.
  const out = document.createElement('canvas')
  out.width = REPORT_W * scale
  out.height = Math.round(contentH * scale)
  const octx = out.getContext('2d')!
  octx.drawImage(full, 0, 0)

  return await new Promise<Blob | null>(resolve => {
    out.toBlob(blob => resolve(blob), 'image/png')
  })
}

/** Wrapper navigateur : dessine le bilan et déclenche le téléchargement du PNG. */
export async function exportWeeklyReportPNG(data: WeeklyReportData): Promise<void> {
  const blob = await renderWeeklyReportBlob(data)
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `bilan-reseaux-${new Date().toISOString().slice(0, 10)}.png`
  a.click()
  URL.revokeObjectURL(url)
}

// Texte multi-ligne avec ellipse sur la dernière ligne.
function wrapText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxW: number, lineH: number, maxLines: number) {
  const words = text.split(' ')
  let line = ''
  let lines = 0
  for (let i = 0; i < words.length; i++) {
    const test = line ? line + ' ' + words[i] : words[i]
    if (ctx.measureText(test).width > maxW && line) {
      if (lines === maxLines - 1) {
        // dernière ligne : tronquer
        let t = line
        while (ctx.measureText(t + '…').width > maxW && t.length) t = t.slice(0, -1)
        ctx.fillText(t + '…', x, y); return
      }
      ctx.fillText(line, x, y); y += lineH; line = words[i]; lines++
    } else {
      line = test
    }
  }
  ctx.fillText(line, x, y)
}
