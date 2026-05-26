'use client'

import { useState } from 'react'
import { createShareLink } from '../../lib/api'

type Props = {
  affairId: string
  /** style compact (icône seule) pour les cartes de liste */
  compact?: boolean
  className?: string
}

/**
 * Génère un lien de partage public pour une affaire (backend: /api/affairs/share/:id),
 * le copie dans le presse-papier et confirme. Le lien pointe vers /share/[token].
 */
export function ShareAffairButton({ affairId, compact = false, className = '' }: Props) {
  const [state, setState] = useState<'idle' | 'loading' | 'copied' | 'error'>('idle')

  const handleShare = async (e: React.MouseEvent) => {
    // utile si le bouton est dans une carte cliquable (Link)
    e.preventDefault()
    e.stopPropagation()
    if (state === 'loading') return
    setState('loading')
    try {
      const res = await createShareLink(affairId)
      const url = res.share_url || `${window.location.origin}/share/${res.share_token}`
      try {
        await navigator.clipboard.writeText(url)
      } catch {
        window.prompt('Copier le lien de partage :', url)
      }
      setState('copied')
      setTimeout(() => setState('idle'), 2500)
    } catch {
      setState('error')
      setTimeout(() => setState('idle'), 2500)
    }
  }

  const label =
    state === 'loading' ? 'Génération…'
    : state === 'copied' ? 'Lien copié'
    : state === 'error' ? 'Erreur'
    : 'Partager'

  const color = state === 'copied' ? 'var(--positive)' : state === 'error' ? 'var(--negative)' : 'var(--text-secondary)'

  return (
    <button
      onClick={handleShare}
      disabled={state === 'loading'}
      title="Générer un lien de partage public"
      aria-label="Partager cette affaire"
      className={`inline-flex items-center gap-1.5 ${compact ? 'p-1.5' : 'px-2.5 py-1 text-[11px] font-medium'} rounded-sm transition-colors hover:bg-ink-100 disabled:opacity-50 ${className}`}
      style={{ border: '1px solid var(--border)', color }}
    >
      <svg className={compact ? 'w-3.5 h-3.5' : 'w-3 h-3'} fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        {state === 'copied' ? (
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.7 10.7l6.6-3.4M8.7 13.3l6.6 3.4M18 5a3 3 0 11-6 0 3 3 0 016 0zM6 12a3 3 0 11-6 0 3 3 0 016 0zm12 7a3 3 0 11-6 0 3 3 0 016 0z" />
        )}
      </svg>
      {!compact && <span>{label}</span>}
    </button>
  )
}
