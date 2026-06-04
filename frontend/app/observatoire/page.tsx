'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import { SocialEvolutionPanel } from '../_components/dashboard/SocialEvolutionPanel'
import { StatsEntryModal } from '../_components/dashboard/StatsEntryModal'
import { DecisionInsights } from '../_components/dashboard/DecisionInsights'
import {
  triggerSocialSnapshot,
  backfillMediaCache,
  sendReportImage,
  fetchWebHistory,
  fetchSocialEvolution,
  fetchDecisionInsights,
  fetchSocialHistory,
  apiErrorMessage,
  type WebTrafficPoint,
  type SocialEvolution,
  type DecisionInsights as DecisionInsightsData,
  type AccountSnapshot,
} from '../../lib/api'
import { exportWeeklyReportPNG, renderWeeklyReportBlob } from '../../lib/weeklyReport'

function fmt(n?: number | null): string {
  if (n === null || n === undefined) return '—'
  if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'k'
  return String(Math.round(n))
}

// Trois horizons d'analyse : semaine, mois, évolution globale (12 mois).
const PERIODS: { d: number; label: string; title: string }[] = [
  { d: 7, label: 'Semaine', title: '7 derniers jours' },
  { d: 30, label: 'Mois', title: '30 derniers jours' },
  { d: 365, label: '12 mois', title: 'Évolution globale (12 derniers mois)' },
]

/** Libellé lisible d'un horizon (ex. 365 → « 12 derniers mois »). */
function periodLabel(days: number): string {
  if (days >= 365) return '12 derniers mois'
  return `${days} derniers jours`
}

// ── Navigation de la période d'observation (date de fin) ──
const isoDay = (d: Date) => d.toISOString().slice(0, 10)
const todayIso = () => isoDay(new Date())

/** Décale une date (YYYY-MM-DD, ou aujourd'hui si null) de `delta` jours. */
function shiftDay(end: string | null, delta: number): string {
  const d = end ? new Date(end + 'T00:00:00') : new Date()
  d.setDate(d.getDate() + delta)
  return isoDay(d)
}

/** Plage observée « 19 mai → 25 mai 2026 » pour un horizon donné. */
function rangeLabel(end: string | null, days: number): string {
  const endD = end ? new Date(end + 'T00:00:00') : new Date()
  const startD = new Date(endD)
  startD.setDate(startD.getDate() - days)
  const f = (d: Date, withYear: boolean) =>
    d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', ...(withYear ? { year: 'numeric' } : {}) })
  return `${f(startD, startD.getFullYear() !== endD.getFullYear())} → ${f(endD, true)}`
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
  const [webPrev, setWebPrev] = useState<WebTrafficPoint | null>(null)
  const [evolution, setEvolution] = useState<SocialEvolution | null>(null)
  const [insights, setInsights] = useState<DecisionInsightsData | null>(null)
  const [history, setHistory] = useState<Record<string, AccountSnapshot[]>>({})
  const [days, setDays] = useState(7)
  // Date de fin de la fenêtre d'observation (null = aujourd'hui).
  const [endDate, setEndDate] = useState<string | null>(null)

  const loadData = useCallback(() => {
    // Trafic web : on garde une fenêtre ≥ 90j pour toujours disposer du
    // dernier point (saisi manuellement, parfois espacé) et de sa tendance.
    fetchWebHistory(Math.max(days, 90), endDate).then(r => {
      setWeb(r.latest)
      // avant-dernier point (pour les tendances du bilan)
      const pts = r.points || []
      setWebPrev(pts.length >= 2 ? pts[pts.length - 2] : null)
    }).catch(() => {})
    fetchSocialEvolution().then(setEvolution).catch(() => {})
    fetchDecisionInsights(days, endDate).then(setInsights).catch(() => {})
    // L'historique social suit l'horizon et la période choisis.
    fetchSocialHistory(undefined, days, endDate).then(r => setHistory(r.series || {})).catch(() => {})
  }, [days, endDate])

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

  const [backfilling, setBackfilling] = useState(false)
  const handleBackfill = async () => {
    setBackfilling(true); setMsg(null)
    try {
      const r = await backfillMediaCache()
      setMsg(`Vignettes mises en cache : ${r.cached} OK, ${r.failed} échecs, ${r.skipped} déjà à jour (${r.scanned} analysés)`)
    } catch (e) {
      setMsg(apiErrorMessage(e, 'mise en cache des vignettes'))
    } finally { setBackfilling(false) }
  }

  const [sendingDigest, setSendingDigest] = useState(false)
  const handleSendPng = async () => {
    setSendingDigest(true); setMsg(null)
    try {
      const blob = await renderWeeklyReportBlob({ web, webPrev, evolution, insights, history })
      if (!blob) { setMsg('Impossible de générer le PNG'); return }
      const caption = `📊 Bilan réseaux sociaux — ${periodLabel(days)}`
      const r = await sendReportImage(blob, caption)
      setMsg(r.sent ? 'Bilan PNG envoyé sur Telegram ✓' : (r.error || 'Envoi du bilan échoué'))
    } catch (e) {
      setMsg(apiErrorMessage(e, 'envoi du bilan Telegram'))
    } finally { setSendingDigest(false) }
  }

  const [exporting, setExporting] = useState(false)
  const handleExport = async () => {
    setExporting(true)
    try {
      await exportWeeklyReportPNG({ web, webPrev, evolution, insights, history })
    } finally {
      setExporting(false)
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
                Évolution de l'engagement, des abonnés et du trafic web
              </p>
              <p className="font-mono text-[11px] mt-1" style={{ color: 'var(--accent)' }}>
                Période observée : {rangeLabel(endDate, days)}{!endDate && ' (en cours)'}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
              {msg && <span className="font-mono text-[11px] w-full text-right mb-1" style={{ color: 'var(--text-muted)' }}>{msg}</span>}
              <div className="inline-flex rounded-sm overflow-hidden" style={{ border: '1px solid var(--border)' }} role="group" aria-label="Horizon d'analyse">
                {PERIODS.map(({ d, label, title }) => (
                  <button key={d} onClick={() => setDays(d)} title={title}
                    className="px-2.5 py-1.5 text-xs font-medium transition-colors"
                    style={days === d
                      ? { background: 'var(--accent-press)', color: 'var(--on-accent)' }
                      : { background: 'var(--bg-surface)', color: 'var(--text-secondary)' }}>
                    {label}
                  </button>
                ))}
              </div>

              {/* Période d'observation : navigation ◀ ▶ + choix d'une date de fin */}
              <div className="inline-flex items-center rounded-sm overflow-hidden" style={{ border: '1px solid var(--border)' }} role="group" aria-label="Période d'observation">
                <button onClick={() => setEndDate(shiftDay(endDate, -days))}
                  title="Période précédente" aria-label="Période précédente"
                  className="px-2 py-1.5 text-xs transition-colors"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)' }}>◀</button>
                <input type="date" value={endDate ?? todayIso()} max={todayIso()}
                  onChange={e => setEndDate(e.target.value >= todayIso() ? null : e.target.value)}
                  title={`Fin de la période observée — ${rangeLabel(endDate, days)}`}
                  className="px-1 py-1 text-xs font-medium bg-transparent outline-none"
                  style={{ color: 'var(--text-secondary)', colorScheme: 'dark' }} />
                <button onClick={() => { const n = shiftDay(endDate, days); setEndDate(n >= todayIso() ? null : n) }}
                  disabled={!endDate}
                  title="Période suivante" aria-label="Période suivante"
                  className="px-2 py-1.5 text-xs transition-colors disabled:opacity-30"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)' }}>▶</button>
                <button onClick={() => setEndDate(null)} disabled={!endDate}
                  title="Revenir à aujourd'hui"
                  className="px-2 py-1.5 text-[11px] font-medium transition-colors disabled:opacity-30"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)', borderLeft: '1px solid var(--border)' }}>
                  Aujourd'hui
                </button>
              </div>
              <button onClick={() => setShowEntry(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                Saisir des stats
              </button>
              <button onClick={handleExport} disabled={exporting}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors disabled:opacity-50"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                {exporting ? 'Génération…' : 'Exporter PNG hebdo'}
              </button>
              <button onClick={handleBackfill} disabled={backfilling}
                title="Met en cache les vignettes des posts (corrige les images manquantes du bilan)"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors disabled:opacity-50"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                {backfilling ? 'Mise en cache…' : 'Cacher les vignettes'}
              </button>
              <button onClick={handleSendPng} disabled={sendingDigest}
                title="Génère le PNG du bilan et l'envoie sur Telegram"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors disabled:opacity-50"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                {sendingDigest ? 'Envoi…' : 'Envoyer PNG sur Telegram'}
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
          <DecisionInsights days={days} />

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
          <SocialEvolutionPanel key={refreshKey} days={days} end={endDate} />

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
