'use client'

import { useState } from 'react'
import Sidebar from '../../components/Sidebar'
import { SocialEvolutionPanel } from '../_components/dashboard/SocialEvolutionPanel'
import { triggerSocialSnapshot } from '../../lib/api'

export default function ObservatoirePage() {
  const [capturing, setCapturing] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  // Force le remontage du panneau après une capture pour rafraîchir les données.
  const [refreshKey, setRefreshKey] = useState(0)

  const handleCapture = async () => {
    setCapturing(true)
    setMsg(null)
    try {
      const r = await triggerSocialSnapshot()
      setMsg(`Instantané capturé (${r.snapshot_date}) — ${r.captured} plateformes`)
      setRefreshKey(k => k + 1)
    } catch {
      setMsg("Capture impossible — réservé aux administrateurs ?")
    } finally {
      setCapturing(false)
    }
  }

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Veille / Réseaux sociaux
              </div>
              <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
                Observatoire
              </h1>
              <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                Évolution de l'engagement et des abonnés dans le temps
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              {msg && (
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>{msg}</span>
              )}
              <button
                onClick={handleCapture}
                disabled={capturing}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-sm transition-colors disabled:opacity-50"
                style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}
              >
                {capturing ? 'Capture…' : 'Capturer maintenant'}
              </button>
            </div>
          </div>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1700px] mx-auto space-y-5">
          <SocialEvolutionPanel key={refreshKey} />

          <p className="font-mono text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            L'engagement est figé chaque soir, les abonnés une fois par semaine. L'historique se
            construit jour après jour — « Capturer maintenant » enregistre un instantané immédiat
            pour amorcer la courbe.
          </p>
        </div>
      </main>
    </div>
  )
}
