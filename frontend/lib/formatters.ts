// lib/formatters.ts — Fonctions utilitaires partagées

/**
 * Formatage "il y a X" depuis une date ISO
 */
export function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  if (isNaN(then)) return ''
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return "à l'instant"
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

/**
 * Label lisible pour un thème
 */
const THEME_LABELS: Record<string, string> = {
  politique: 'Politique', economie: 'Économie', social: 'Social',
  economie_emploi: 'Économie', eau_env: 'Environnement',
  energie_transports: 'Transports', sante_social: 'Santé',
  securite_justice: 'Justice', education: 'Éducation',
  culture_patrimoine: 'Culture', sport: 'Sport', general: 'Général',
  environnement: 'Environnement', sante: 'Santé', justice: 'Justice',
  culture: 'Culture', securite: 'Sécurité', infrastructure: 'Infra',
}

export function themeLabel(theme: string): string {
  return THEME_LABELS[theme] || theme
}

/**
 * Couleurs pour un thème — [bg, color, border]
 */
const THEME_COLORS: Record<string, string> = {
  politique: 'rgba(168,85,247,0.15)_#c084fc_rgba(168,85,247,0.3)',
  economie: 'rgba(16,185,129,0.15)_#34d399_rgba(16,185,129,0.3)',
  economie_emploi: 'rgba(16,185,129,0.15)_#34d399_rgba(16,185,129,0.3)',
  social: 'rgba(96,165,250,0.15)_#93c5fd_rgba(96,165,250,0.3)',
  sante_social: 'rgba(251,113,133,0.15)_#fda4af_rgba(251,113,133,0.3)',
  environnement: 'rgba(74,222,128,0.15)_#86efac_rgba(74,222,128,0.3)',
  eau_env: 'rgba(74,222,128,0.15)_#86efac_rgba(74,222,128,0.3)',
  sante: 'rgba(251,113,133,0.15)_#fda4af_rgba(251,113,133,0.3)',
  justice: 'rgba(251,191,36,0.15)_#fde68a_rgba(251,191,36,0.3)',
  securite_justice: 'rgba(251,191,36,0.15)_#fde68a_rgba(251,191,36,0.3)',
  securite: 'rgba(248,113,113,0.15)_#fca5a5_rgba(248,113,113,0.3)',
  education: 'rgba(129,140,248,0.15)_#a5b4fc_rgba(129,140,248,0.3)',
  culture: 'rgba(244,114,182,0.15)_#f9a8d4_rgba(244,114,182,0.3)',
  culture_patrimoine: 'rgba(244,114,182,0.15)_#f9a8d4_rgba(244,114,182,0.3)',
  sport: 'rgba(34,211,238,0.15)_#67e8f9_rgba(34,211,238,0.3)',
  infrastructure: 'rgba(251,146,60,0.15)_#fdba74_rgba(251,146,60,0.3)',
  energie_transports: 'rgba(251,146,60,0.15)_#fdba74_rgba(251,146,60,0.3)',
}

export function themeColorParts(theme: string): [string, string, string] {
  const raw = THEME_COLORS[theme] || 'rgba(148,163,184,0.15)_#cbd5e1_rgba(148,163,184,0.3)'
  return raw.split('_') as [string, string, string]
}

/**
 * Classe CSS pour la gravité
 */
export function gravityClass(score: number): string {
  if (score >= 0.7) return 'bg-red-500/20 text-red-400'
  if (score >= 0.5) return 'bg-orange-500/20 text-orange-400'
  if (score >= 0.3) return 'bg-yellow-500/20 text-yellow-400'
  return 'bg-emerald-500/20 text-emerald-400'
}

/**
 * Label pour la gravité
 */
export function gravityLabel(score: number): string {
  if (score >= 0.85) return 'CRITIQUE'
  if (score >= 0.7) return 'GRAVE'
  if (score >= 0.5) return 'MODÉRÉ'
  if (score >= 0.3) return 'FAIBLE'
  return 'MINIMAL'
}

/**
 * Couleur pour le sentiment
 */
export function sentimentColor(sentiment: string): string {
  const s = (sentiment || '').toLowerCase()
  if (s.includes('négatif') || s.includes('negatif')) return '#f87171'
  if (s.includes('positif')) return '#6ee7b7'
  if (s.includes('mixte')) return '#fbbf24'
  return '#818cf8'
}

/**
 * Emoji pour le sentiment
 */
export function sentimentEmoji(sentiment: string): string {
  const s = (sentiment || '').toLowerCase()
  if (s.includes('négatif') || s.includes('negatif')) return '😠'
  if (s.includes('positif')) return '😊'
  if (s.includes('mixte')) return '🤔'
  return ''
}
