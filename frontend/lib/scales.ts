/**
 * Editorial scales — shared color + label scales for sentiment & gravity.
 *
 * - Sentiment: 3 buckets only (positive / negative / neutral) — "mixed/mitigé"
 *   collapses into neutral to avoid rainbow listings.
 * - Gravity (BMG): 4 buckets — granularity needed for BMG-driven decisions.
 */

export type SentimentBucket = 'positive' | 'negative' | 'neutral'
export type GravityBucket = 'low' | 'medium' | 'high' | 'critical'

export type StylePair = { bg: string; color: string; border: string }

/* ── Sentiment ─────────────────────────────────────────── */

export function sentimentBucket(raw?: string): SentimentBucket {
  const s = (raw || '').toLowerCase()
  if (s.includes('positif') || s.includes('positive')) return 'positive'
  if (s.includes('négatif') || s.includes('negatif') || s.includes('negative')) return 'negative'
  return 'neutral'
}

export const SENTIMENT_STYLE: Record<SentimentBucket, StylePair> = {
  positive: { bg: 'var(--ok-soft)',     color: '#3d6f44', border: '#cce5d0' },
  negative: { bg: 'var(--crit-soft)',   color: '#8a2438', border: '#f0c6cd' },
  neutral:  { bg: 'var(--bg-elevated)', color: 'var(--text-muted)', border: 'var(--border)' },
}

export function sentimentLabel(b: SentimentBucket): string {
  switch (b) {
    case 'positive': return 'Positif'
    case 'negative': return 'Négatif'
    default:         return 'Neutre'
  }
}

/* ── Gravity / BMG ─────────────────────────────────────── */

export function gravityBucket(g: number): GravityBucket {
  if (g >= 70) return 'critical'
  if (g >= 50) return 'high'
  if (g >= 25) return 'medium'
  return 'low'
}

export function gravityColor(g: number): string {
  const b = gravityBucket(g)
  if (b === 'critical') return 'var(--negative)'
  if (b === 'high')     return 'var(--warning)'
  if (b === 'medium')   return 'var(--caution)'
  return 'var(--positive)'
}

export function gravityLabel(g: number): string {
  const b = gravityBucket(g)
  if (b === 'critical') return 'CRITIQUE'
  if (b === 'high')     return 'ÉLEVÉ'
  if (b === 'medium')   return 'MODÉRÉ'
  return 'FAIBLE'
}
