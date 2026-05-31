'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import { SocialEvolutionPanel } from '../_components/dashboard/SocialEvolutionPanel'
import { StatsEntryModal } from '../_components/dashboard/StatsEntryModal'
import { DecisionInsights } from '../_components/dashboard/DecisionInsights'
import {
  triggerSocialSnapshot,
  fetchWebHistory,
  fetchSocialEvolution,
  fetchDecisionInsights,
  apiErrorMessage,
  type WebTrafficPoint,
  type SocialEvolution,
  type DecisionInsights as DecisionInsightsData,
} from '../../lib/api'
import { exportWeeklyReportPNG } from '../../lib/weeklyReport'

function fmt(n?: number | null): string {
  if (n === null || n === undefined) return '—'
  if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'k'
  return String(Math.round(n))
}

const WEB_CARDS: { key: keyof WebTrafficPoint; label: string; suffix?: string }[] = [
  { key: 'sessions', label: 'Sessions' },
  { key: 'pageviews', label: 'Pages vues' },
  { key: 'users', label: 'Utilisateurs' },
  { key: 'new_users', label: 'Nouveaux' },
  { key: 'avg_session_duration', label: 'Durée moy.', suffix: 's' },
  { key: 'bounce_rate', label: 'Rebond', suffix: '%' },
]

export default function ObservatoirePage() {
  const [capturing, setCapturing] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [showEntry, setShowEntry] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const [web, setWeb] = useState<WebTrafficPoint | null>(null)
  const [evolution, setEvolution] = useState<SocialEvolution | null>(null)
  const [insights, setInsights] = useState<DecisionInsightsData | null>(null)

  const loadData = useCallback(() => {
    fetchWebHistory(90).then(r => setWeb(r.latest)).catch(() => {})
    fetchSocialEvolution().then(setEvolution).catch(() => {})
    fetchDecisionInsights(7).then(setInsights).catch(() => {})
  }, [])

  useEffect(() => { loadData() }, [loadData, refreshKey])

  const handleCapture = async () => {
    setCapturing(true); setMsg(null)
    try {
      const r = await triggerSocialSnapshot()
      setMsg(`Instantané capturé (${r.snapshot_date}) — ${r.captured} plateformes`)
      setRefreshKey(k => k + 1)
    } catch (e) {
      setMsg(apiErrorMessage(e, 'capture'))
    } finally { setCapturing(false) }
  }

  const handleExport = () => {
    exportWeeklyReportPNG({ web, evolution, insights })
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
                Évolution de l'engagement, des abonnés et du trafic web
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
              {msg && <span className="font-mono text-[11px] w-full text-right mb-1" style={{ color: 'var(--text-muted)' }}>{msg}</span>}
              <button onClick={() => setShowEntry(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                Saisir des stats
              </button>
              <button onClick={handleExport}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                Exporter PNG hebdo
              </button>
              <button onClick={handleCapture} disabled={capturing}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-sm transition-colors disabled:opacity-50"
                style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}>
                {capturing ? 'Capture…' : 'Capturer maintenant'}
              </button>
            </div>
          </div>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1700px] mx-auto space-y-5">
          {/* Outil de décision : top post, ce qui marche, sentiment, top 3 */}
          <DecisionInsights days={7} />

          {/* Trafic web (saisi manuellement) */}
          <div className="rounded-2xl p-5" style={{ background: 'rgba(255,255,255,0.03)' }}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white/80">Trafic du site web</h3>
              <span className="text-[10px] text-white/30">
                {web?.snapshot_date ? `saisi le ${web.snapshot_date}` : 'aucune saisie — bouton « Saisir des stats »'}
              </span>
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
              {WEB_CARDS.map(c => (
                <div key={String(c.key)} className="rounded-xl p-3" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div className="text-[10px] text-white/40 mb-1">{c.label}</div>
                  <div className="text-lg font-bold text-white tabular-nums">
                    {web && web[c.key] != null ? `${fmt(web[c.key] as number)}${c.suffix ?? ''}` : '—'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Évolution sociale */}
          <SocialEvolutionPanel key={refreshKey} />

          <p className="font-mono text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            L'engagement est figé chaque soir, les abonnés une fois par semaine. Le trafic web et les
            abonnés se saisissent à la main (« Saisir des stats »). « Exporter PNG hebdo » génère une
            carte bilan combinant trafic, engagement et campagnes.
          </p>
        </div>
      </main>

      {showEntry && (
        <StatsEntryModal
          onClose={() => setShowEntry(false)}
          onSaved={() => { setRefreshKey(k => k + 1) }}
        />
      )}
    </div>
  )
}
