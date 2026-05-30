// Génère un PNG « bilan hebdomadaire » combinant trafic web, engagement social
// et campagnes — dessiné sur un canvas natif (aucune dépendance externe).

import type { SocialEvolution, WebTrafficPoint, Campaign } from './api'

export interface WeeklyReportData {
  web: WebTrafficPoint | null
  evolution: SocialEvolution | null
  campaigns: Campaign[]
}

const PLAT_COLORS: Record<string, string> = {
  instagram: '#e4405f',
  facebook: '#1877f2',
  tiktok: '#00f2ea',
}

function fmt(n?: number | null): string {
  if (n === null || n === undefined) return '—'
  if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'k'
  return String(Math.round(n))
}

function frDate(d: Date): string {
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}

/** Dessine la carte bilan et déclenche le téléchargement du PNG. */
export function exportWeeklyReportPNG(data: WeeklyReportData): void {
  const W = 1200
  const H = 1500
  const scale = 2 // rendu net (retina)
  const canvas = document.createElement('canvas')
  canvas.width = W * scale
  canvas.height = H * scale
  const ctx = canvas.getContext('2d')!
  ctx.scale(scale, scale)

  // Fond dark cohérent avec « Carte vivante »
  const bg = ctx.createLinearGradient(0, 0, 0, H)
  bg.addColorStop(0, '#0a1822')
  bg.addColorStop(1, '#07141c')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, W, H)

  const PAD = 64
  let y = 0

  // ── En-tête ──
  ctx.fillStyle = '#5FD0E0'
  ctx.font = '600 13px Inter, system-ui, sans-serif'
  ctx.fillText('OBSERVATOIRE · BILAN HEBDOMADAIRE', PAD, 70)

  ctx.fillStyle = '#ffffff'
  ctx.font = '700 42px Georgia, serif'
  ctx.fillText('Conseil Départemental', PAD, 122)
  ctx.fillText('de la Guadeloupe', PAD, 172)

  const now = new Date()
  const weekAgo = new Date(now.getTime() - 7 * 86400000)
  ctx.fillStyle = 'rgba(255,255,255,0.45)'
  ctx.font = '400 16px Inter, system-ui, sans-serif'
  ctx.fillText(`Semaine du ${frDate(weekAgo)} au ${frDate(now)}`, PAD, 210)

  y = 268

  // ── Section helper ──
  const sectionTitle = (label: string) => {
    ctx.fillStyle = 'rgba(255,255,255,0.5)'
    ctx.font = '600 13px Inter, system-ui, sans-serif'
    ctx.fillText(label.toUpperCase(), PAD, y)
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(PAD, y + 14); ctx.lineTo(W - PAD, y + 14); ctx.stroke()
    y += 44
  }

  // ── Trafic web ──
  sectionTitle('Trafic du site web')
  const web = data.web
  const webCells: [string, string][] = [
    ['Sessions', fmt(web?.sessions)],
    ['Pages vues', fmt(web?.pageviews)],
    ['Utilisateurs', fmt(web?.users)],
    ['Nouveaux', fmt(web?.new_users)],
    ['Durée moy.', web?.avg_session_duration != null ? `${Math.round(web.avg_session_duration)}s` : '—'],
    ['Rebond', web?.bounce_rate != null ? `${web.bounce_rate}%` : '—'],
  ]
  const colW = (W - PAD * 2) / 3
  webCells.forEach((cell, i) => {
    const cx = PAD + (i % 3) * colW
    const cy = y + Math.floor(i / 3) * 96
    ctx.fillStyle = 'rgba(255,255,255,0.4)'
    ctx.font = '400 14px Inter, system-ui, sans-serif'
    ctx.fillText(cell[0], cx, cy + 4)
    ctx.fillStyle = '#ffffff'
    ctx.font = '700 34px Inter, system-ui, sans-serif'
    ctx.fillText(cell[1], cx, cy + 44)
  })
  y += 96 * 2 + 24

  // ── Engagement social ──
  sectionTitle('Engagement réseaux sociaux')
  const platforms = ['instagram', 'facebook', 'tiktok']
  platforms.forEach((p, i) => {
    const e = data.evolution?.platforms?.[p]
    const cx = PAD + i * colW
    ctx.fillStyle = PLAT_COLORS[p]
    ctx.font = '600 16px Inter, system-ui, sans-serif'
    ctx.fillText(p.charAt(0).toUpperCase() + p.slice(1), cx, y + 4)

    ctx.fillStyle = '#ffffff'
    ctx.font = '700 30px Inter, system-ui, sans-serif'
    ctx.fillText(fmt(e?.engagement), cx, y + 42)

    ctx.fillStyle = 'rgba(255,255,255,0.4)'
    ctx.font = '400 13px Inter, system-ui, sans-serif'
    ctx.fillText('engagement', cx, y + 64)

    const followers = e?.followers
    ctx.fillStyle = 'rgba(255,255,255,0.7)'
    ctx.font = '500 15px Inter, system-ui, sans-serif'
    ctx.fillText(`${fmt(followers)} abonnés`, cx, y + 92)

    // delta 7j
    const d7 = e?.delta_engagement_7d
    if (d7 != null) {
      const up = d7 > 0
      ctx.fillStyle = d7 === 0 ? 'rgba(255,255,255,0.4)' : up ? '#34d399' : '#f87171'
      ctx.font = '600 13px Inter, system-ui, sans-serif'
      ctx.fillText(`${up ? '▲' : d7 === 0 ? '→' : '▼'} ${fmt(Math.abs(d7))} / 7j`, cx, y + 116)
    }
  })
  y += 150

  // ── Campagnes ──
  sectionTitle('Campagnes actives')
  const active = data.campaigns.filter(c => c.status === 'active').slice(0, 4)
  if (active.length === 0) {
    ctx.fillStyle = 'rgba(255,255,255,0.4)'
    ctx.font = '400 16px Inter, system-ui, sans-serif'
    ctx.fillText('Aucune campagne active cette semaine.', PAD, y + 8)
    y += 40
  } else {
    active.forEach(c => {
      ctx.fillStyle = '#ffffff'
      ctx.font = '600 18px Inter, system-ui, sans-serif'
      ctx.fillText(c.name, PAD, y + 8)
      ctx.fillStyle = 'rgba(255,255,255,0.55)'
      ctx.font = '400 15px Inter, system-ui, sans-serif'
      const line = `${c.post_count} posts · ${fmt(c.total_views)} vues · ${fmt(c.total_likes)} likes · ${fmt(c.total_comments)} commentaires`
      ctx.fillText(line, PAD, y + 34)
      y += 64
    })
  }

  // ── Pied de page ──
  ctx.fillStyle = 'rgba(255,255,255,0.3)'
  ctx.font = '400 13px Inter, system-ui, sans-serif'
  ctx.fillText(`Généré le ${frDate(now)} · Observatoire interne`, PAD, H - 48)

  // Téléchargement
  canvas.toBlob(blob => {
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `bilan-hebdo-${now.toISOString().slice(0, 10)}.png`
    a.click()
    URL.revokeObjectURL(url)
  }, 'image/png')
}
