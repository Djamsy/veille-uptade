'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchRadioCardsToday,
  fetchRadioCards,
  captureRadioNow,
  refreshRadioSnapshot,
  fetchRadioDebugStreams,
  fetchRadioHealthCheck,
  fetchRadioHealthCheckSingle,
  type RadioCard,
  type StreamHealthResult,
  type StreamHealthResponse,
} from '../../lib/api'

// ============================================================
// Helpers
// ============================================================

function timeAgo(dateStr?: string) {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'à l\'instant'
  if (mins < 60) return `il y a ${mins}min`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `il y a ${hrs}h`
  return `il y a ${Math.floor(hrs / 24)}j`
}

function sourceBadgeColor(source?: string) {
  if (!source) return 'bg-purple-500 bg-opacity-15 text-purple-300 border border-purple-500 border-opacity-30'
  const s = source.toLowerCase()
  if (s.includes('rci')) return 'bg-amber-500 bg-opacity-15 text-amber-300 border border-amber-500 border-opacity-30'
  if (s.includes('guadeloupe') || s.includes('gp')) return 'bg-blue-500 bg-opacity-15 text-blue-300 border border-blue-500 border-opacity-30'
  return 'bg-purple-500 bg-opacity-15 text-purple-300 border border-purple-500 border-opacity-30'
}

function summarySourceLabel(src: string) {
  if (src === 'gpt') return 'Résumé IA'
  return 'Transcription'
}

// ============================================================
// Components
// ============================================================

function SkeletonCard() {
  return (
    <div className="skeleton glass-card-static p-5 animate-pulse">
      <div className="h-4 bg-white bg-opacity-20 rounded w-3/4 mb-3" />
      <div className="h-3 bg-white bg-opacity-15 rounded w-1/2 mb-4" />
      <div className="space-y-2">
        <div className="h-3 bg-white bg-opacity-15 rounded w-full" />
        <div className="h-3 bg-white bg-opacity-15 rounded w-5/6" />
        <div className="h-3 bg-white bg-opacity-15 rounded w-2/3" />
      </div>
    </div>
  )
}

function RadioCardItem({
  card,
  expanded,
  onToggle,
}: {
  card: RadioCard
  expanded: boolean
  onToggle: () => void
}) {
  const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

  return (
    <div className="glass-card rounded-xl">
      {/* Header */}
      <div className="px-5 pt-5 pb-3">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white truncate">{card.title}</h3>
            <p className="text-xs text-white text-opacity-50 mt-0.5">{card.subtitle}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${sourceBadgeColor(card.source)}`}>
              {card.source || 'Radio'}
            </span>
            <span className="text-[10px] text-white text-opacity-35">{timeAgo(card.capturedAt)}</span>
          </div>
        </div>

        {/* Summary source badge */}
        <div className="flex items-center gap-2 mb-3">
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
            card.summarySource === 'gpt'
              ? 'bg-emerald-500 bg-opacity-10 text-emerald-300'
              : 'bg-white bg-opacity-5 text-white text-opacity-35'
          }`}>
            {summarySourceLabel(card.summarySource)}
          </span>
          {card.meta?.transcriptionMethod && (
            <span className="text-[10px] text-white text-opacity-35">
              {card.meta.transcriptionMethod}
            </span>
          )}
        </div>

        {/* Summary text */}
        <div className="text-sm text-white text-opacity-50 leading-relaxed">
          {expanded && card.fullText ? card.fullText : card.summary}
        </div>
        {card.isTruncated && (
          <button
            onClick={onToggle}
            className="mt-2 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            {expanded ? '▲ Réduire' : '▼ Voir tout'}
          </button>
        )}
      </div>

      {/* Audio player */}
      {card.audioUrl && (
        <div className="px-5 pb-4 pt-1 border-t border-white border-opacity-6">
          <audio
            controls
            preload="none"
            className="w-full h-8"
            style={{ opacity: 0.9, filter: 'invert(1) hue-rotate(180deg)' }}
          >
            <source src={`${BACKEND_URL}${card.audioUrl}`} type="audio/wav" />
          </audio>
        </div>
      )}
    </div>
  )
}

// ============================================================
// Stream Health Panel
// ============================================================

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  ok:       { label: 'OK',         color: 'text-emerald-400', bg: 'bg-emerald-500', icon: '●' },
  warning:  { label: 'Attention',  color: 'text-amber-400',   bg: 'bg-amber-500',   icon: '▲' },
  error:    { label: 'Erreur',     color: 'text-red-400',     bg: 'bg-red-500',     icon: '✕' },
  disabled: { label: 'Désactivé',  color: 'text-white text-opacity-30', bg: 'bg-white', icon: '○' },
  unknown:  { label: 'Inconnu',    color: 'text-white text-opacity-40', bg: 'bg-white', icon: '?' },
}

function HealthScoreRing({ score }: { score: number }) {
  const r = 28, stroke = 5
  const c = 2 * Math.PI * r
  const offset = c - (score / 100) * c
  const color = score >= 80 ? '#34d399' : score >= 50 ? '#fbbf24' : '#f87171'
  return (
    <svg width="72" height="72" viewBox="0 0 72 72" className="shrink-0">
      <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
      <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
        transform="rotate(-90 36 36)" className="transition-all duration-700" />
      <text x="36" y="36" textAnchor="middle" dominantBaseline="central"
        className="text-sm font-bold" fill={color}>{score}%</text>
    </svg>
  )
}

function StreamHealthPanel({
  healthData,
  checking,
  onCheckAll,
  onCheckSingle,
  checkingSingle,
}: {
  healthData: StreamHealthResponse | null
  checking: boolean
  onCheckAll: () => void
  onCheckSingle: (key: string) => void
  checkingSingle: string | null
}) {
  if (!healthData) {
    return (
      <div className="glass-card-static rounded-xl p-5 text-center">
        <p className="text-sm text-white text-opacity-40 mb-3">
          Aucun health-check effectué
        </p>
        <button onClick={onCheckAll} disabled={checking}
          className="btn-primary px-4 py-2 text-sm font-medium disabled:opacity-50">
          {checking ? '⟳ Vérification...' : '🩺 Lancer le diagnostic'}
        </button>
      </div>
    )
  }

  const { summary, streams, checked_at } = healthData
  const enabledStreams = streams.filter(s => s.status !== 'disabled')
  const disabledStreams = streams.filter(s => s.status === 'disabled')

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="glass-card-static rounded-xl p-5">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4">
            <HealthScoreRing score={summary.health_score} />
            <div>
              <h3 className="text-sm font-semibold text-white">Santé des flux radio</h3>
              <p className="text-xs text-white text-opacity-40 mt-0.5">
                {summary.ok} OK · {summary.warning} attention · {summary.error} erreur{summary.error > 1 ? 's' : ''} · {summary.disabled} désactivé{summary.disabled > 1 ? 's' : ''}
              </p>
              {checked_at && (
                <p className="text-[10px] text-white text-opacity-25 mt-1">
                  Dernière vérif : {new Date(checked_at).toLocaleString('fr-FR')}
                </p>
              )}
            </div>
          </div>
          <button onClick={onCheckAll} disabled={checking}
            className="btn-glass px-3 py-1.5 text-xs font-medium disabled:opacity-50 shrink-0">
            {checking ? (
              <span className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                Vérification...
              </span>
            ) : '🩺 Re-tester tout'}
          </button>
        </div>
      </div>

      {/* Stream cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {enabledStreams.map((stream) => {
          const cfg = STATUS_CONFIG[stream.status] || STATUS_CONFIG.unknown
          const isChecking = checkingSingle === stream.key
          return (
            <div key={stream.key}
              className="glass-card-static rounded-lg p-4 relative overflow-hidden"
              style={{
                borderLeft: `3px solid ${
                  stream.status === 'ok' ? '#34d399' :
                  stream.status === 'warning' ? '#fbbf24' :
                  stream.status === 'error' ? '#f87171' : 'rgba(255,255,255,0.1)'
                }`
              }}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex-1 min-w-0">
                  <h4 className="text-xs font-semibold text-white truncate">{stream.name}</h4>
                  <p className="text-[10px] text-white text-opacity-35 truncate">{stream.section}</p>
                </div>
                <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${cfg.color}`}
                  style={{ backgroundColor: stream.status === 'ok' ? 'rgba(52,211,153,0.1)' :
                    stream.status === 'warning' ? 'rgba(251,191,36,0.1)' :
                    stream.status === 'error' ? 'rgba(248,113,113,0.1)' : 'rgba(255,255,255,0.05)' }}>
                  {cfg.icon} {cfg.label}
                </span>
              </div>

              {/* Détails */}
              <div className="space-y-1 mb-2">
                {stream.latency_ms !== null && (
                  <div className="flex justify-between text-[10px]">
                    <span className="text-white text-opacity-35">Latence</span>
                    <span className={stream.latency_ms > 3000 ? 'text-amber-400' : 'text-white text-opacity-60'}>
                      {stream.latency_ms}ms
                    </span>
                  </div>
                )}
                {stream.content_type && (
                  <div className="flex justify-between text-[10px]">
                    <span className="text-white text-opacity-35">Type</span>
                    <span className="text-white text-opacity-60 truncate ml-2">{stream.content_type.split(';')[0]}</span>
                  </div>
                )}
                {stream.error && (
                  <p className="text-[10px] text-red-400 mt-1 leading-snug">{stream.error}</p>
                )}
              </div>

              {/* URL + re-test button */}
              <div className="flex items-center justify-between pt-2 border-t border-white border-opacity-5">
                <span className="text-[9px] text-white text-opacity-20 truncate flex-1 mr-2"
                  title={stream.url}>{stream.url}</span>
                <button
                  onClick={() => onCheckSingle(stream.key)}
                  disabled={isChecking}
                  className="text-[10px] text-emerald-400 hover:text-emerald-300 transition-colors disabled:opacity-50 shrink-0"
                >
                  {isChecking ? '⟳' : '↻ Tester'}
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Disabled streams */}
      {disabledStreams.length > 0 && (
        <div className="glass-card-static rounded-lg p-3">
          <p className="text-[10px] text-white text-opacity-25 mb-1">
            {disabledStreams.length} flux désactivé{disabledStreams.length > 1 ? 's' : ''} :
          </p>
          <div className="flex flex-wrap gap-2">
            {disabledStreams.map(s => (
              <span key={s.key} className="text-[10px] text-white text-opacity-20 bg-white bg-opacity-5 px-2 py-0.5 rounded">
                {s.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================
// Main Page
// ============================================================

export default function RadioPage() {
  const [cards, setCards] = useState<RadioCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedDate, setSelectedDate] = useState('')
  const [viewMode, setViewMode] = useState<'today' | 'date'>('today')
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set())
  const [capturing, setCapturing] = useState(false)
  const [captureSection, setCaptureSection] = useState('')
  const [captureDuration, setCaptureDuration] = useState(20)
  const [refreshing, setRefreshing] = useState(false)
  const [total, setTotal] = useState(0)
  const [showCapturePanel, setShowCapturePanel] = useState(false)
  const [showHealthPanel, setShowHealthPanel] = useState(false)
  const [healthData, setHealthData] = useState<StreamHealthResponse | null>(null)
  const [healthChecking, setHealthChecking] = useState(false)
  const [checkingSingle, setCheckingSingle] = useState<string | null>(null)
  const mounted = useRef(true)

  const loadCards = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (viewMode === 'today') {
        const res = await fetchRadioCardsToday(50)
        if (mounted.current) {
          setCards(res.cards || [])
          setTotal(res.cards?.length || 0)
        }
      } else if (selectedDate) {
        const res = await fetchRadioCards(selectedDate, 50, 0)
        if (mounted.current) {
          setCards(res.cards || [])
          setTotal(res.pagination?.total || res.cards?.length || 0)
        }
      }
    } catch (err: any) {
      if (mounted.current) setError(err.message)
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [viewMode, selectedDate])

  useEffect(() => {
    mounted.current = true
    loadCards()
    return () => { mounted.current = false }
  }, [loadCards])

  // Auto-refresh toutes les 2 minutes
  useEffect(() => {
    const interval = setInterval(loadCards, 120000)
    return () => clearInterval(interval)
  }, [loadCards])

  const toggleCard = (id: string) => {
    setExpandedCards((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleCapture = async () => {
    setCapturing(true)
    try {
      const result = await captureRadioNow(captureSection, captureDuration)
      if (result.success && result.card) {
        setCards((prev) => [result.card, ...prev])
        setTotal((prev) => prev + 1)
      }
    } catch (err: any) {
      setError(`Capture échouée: ${err.message}`)
    } finally {
      setCapturing(false)
    }
  }

  const handleRefreshSnapshot = async () => {
    setRefreshing(true)
    try {
      const res = await refreshRadioSnapshot(
        viewMode === 'date' && selectedDate ? selectedDate : undefined
      )
      if (res.success) {
        setCards(res.cards || [])
        setTotal(res.count || 0)
      }
    } catch (err: any) {
      setError(`Refresh snapshot: ${err.message}`)
    } finally {
      setRefreshing(false)
    }
  }

  const handleHealthCheckAll = async () => {
    setHealthChecking(true)
    try {
      const res = await fetchRadioHealthCheck()
      if (mounted.current && res.success) setHealthData(res)
    } catch (err: any) {
      if (mounted.current) setError(`Health-check échoué: ${err.message}`)
    } finally {
      if (mounted.current) setHealthChecking(false)
    }
  }

  const handleHealthCheckSingle = async (key: string) => {
    setCheckingSingle(key)
    try {
      const res = await fetchRadioHealthCheckSingle(key)
      if (mounted.current && res.success && healthData) {
        setHealthData({
          ...healthData,
          streams: healthData.streams.map(s => s.key === key ? res.stream : s),
          checked_at: new Date().toISOString(),
          summary: {
            ...healthData.summary,
            ok: healthData.streams.filter(s => (s.key === key ? res.stream.status : s.status) === 'ok').length,
            warning: healthData.streams.filter(s => (s.key === key ? res.stream.status : s.status) === 'warning').length,
            error: healthData.streams.filter(s => (s.key === key ? res.stream.status : s.status) === 'error').length,
            health_score: Math.round(
              healthData.streams.filter(s => (s.key === key ? res.stream.status : s.status) === 'ok').length /
              Math.max(1, healthData.streams.filter(s => s.status !== 'disabled').length) * 100
            ),
          },
        })
      }
    } catch (err: any) {
      if (mounted.current) setError(`Test ${key} échoué: ${err.message}`)
    } finally {
      if (mounted.current) setCheckingSingle(null)
    }
  }

  return (
    <>
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-4 lg:p-8 pb-24 lg:pb-8 min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Transcriptions Radio</h1>
          <p className="text-sm text-white text-opacity-50 mt-1">
            {total} transcription{total !== 1 ? 's' : ''} • {viewMode === 'today' ? 'Aujourd\'hui' : selectedDate || '—'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Date toggle */}
          <div className="flex rounded-lg border border-white border-opacity-6 overflow-hidden">
            <button
              onClick={() => setViewMode('today')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === 'today'
                  ? 'bg-emerald-500 bg-opacity-20 text-emerald-300 border-r border-white border-opacity-6'
                  : 'text-white text-opacity-50 hover:text-white hover:text-opacity-75 border-r border-white border-opacity-6'
              }`}
            >
              Aujourd&apos;hui
            </button>
            <button
              onClick={() => setViewMode('date')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === 'date'
                  ? 'bg-emerald-500 bg-opacity-20 text-emerald-300'
                  : 'text-white text-opacity-50 hover:text-white hover:text-opacity-75'
              }`}
            >
              Par date
            </button>
          </div>

          {viewMode === 'date' && (
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="input-dark px-3 py-1.5 rounded-lg text-xs"
            />
          )}

          <button
            onClick={handleRefreshSnapshot}
            disabled={refreshing}
            className="btn-glass px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50"
          >
            {refreshing ? '⟳ Refresh...' : '⟳ Snapshot'}
          </button>

          <button
            onClick={() => { setShowHealthPanel(!showHealthPanel); if (!healthData && !showHealthPanel) handleHealthCheckAll() }}
            className={`btn-glass px-3 py-1.5 text-xs font-medium transition-colors ${showHealthPanel ? 'ring-1 ring-emerald-500 ring-opacity-40' : ''}`}
          >
            🩺 Diagnostic
          </button>

          <button
            onClick={() => setShowCapturePanel(!showCapturePanel)}
            className="btn-primary px-3 py-1.5 text-xs font-medium"
          >
            🎙 Capturer
          </button>
        </div>
      </div>

      {/* Capture panel */}
      {showCapturePanel && (
        <div className="glass-card-static rounded-xl p-5" style={{ backgroundColor: 'rgba(16,185,129,0.08)', borderColor: 'rgba(16,185,129,0.2)' }}>
          <h3 className="text-sm font-semibold text-emerald-300 mb-3">Capture radio en direct</h3>
          <div className="flex items-end gap-3 flex-wrap">
            <div>
              <label className="block text-[10px] text-white text-opacity-50 mb-1">Flux / Section</label>
              <input
                type="text"
                value={captureSection}
                onChange={(e) => setCaptureSection(e.target.value)}
                placeholder="rci, guadeloupe, gp..."
                className="input-dark px-3 py-2 text-sm w-48"
              />
            </div>
            <div>
              <label className="block text-[10px] text-white text-opacity-50 mb-1">Durée (sec)</label>
              <input
                type="number"
                value={captureDuration}
                onChange={(e) => setCaptureDuration(Number(e.target.value))}
                min={5}
                max={600}
                className="input-dark px-3 py-2 text-sm w-24"
              />
            </div>
            <button
              onClick={handleCapture}
              disabled={capturing}
              className="btn-primary px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {capturing ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Capture en cours...
                </span>
              ) : 'Lancer la capture'}
            </button>
          </div>
          <p className="mt-2 text-[10px] text-white text-opacity-35">
            Laissez le flux vide pour utiliser le stream prioritaire par défaut (RCI replay).
          </p>
        </div>
      )}

      {/* Health panel */}
      {showHealthPanel && (
        <StreamHealthPanel
          healthData={healthData}
          checking={healthChecking}
          onCheckAll={handleHealthCheckAll}
          onCheckSingle={handleHealthCheckSingle}
          checkingSingle={checkingSingle}
        />
      )}

      {/* Error */}
      {error && (
        <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.2)', color: '#f87171' }}>
          {error}
          <button onClick={() => setError('')} className="ml-3 text-red-400 hover:text-red-300">✕</button>
        </div>
      )}

      {/* Cards grid */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[...Array(6)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : cards.length === 0 ? (
        <div className="glass-card-static rounded-xl p-12 text-center">
          <div className="text-4xl mb-3">📻</div>
          <h3 className="text-lg font-medium text-white text-opacity-50 mb-1">Aucune transcription</h3>
          <p className="text-sm text-white text-opacity-35">
            {viewMode === 'today'
              ? 'Pas encore de transcriptions aujourd\'hui. Lancez une capture !'
              : `Aucune transcription pour le ${selectedDate}`}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {cards.map((card) => (
            <RadioCardItem
              key={card.id}
              card={card}
              expanded={expandedCards.has(card.id)}
              onToggle={() => toggleCard(card.id)}
            />
          ))}
        </div>
      )}

      {/* Stats footer */}
      {!loading && cards.length > 0 && (
        <div className="flex items-center justify-between text-xs text-white text-opacity-35 px-1">
          <span>
            {cards.filter((c) => c.summarySource === 'gpt').length} résumés IA •{' '}
            {cards.filter((c) => c.audioUrl).length} avec audio
          </span>
          <button
            onClick={loadCards}
            className="text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            Actualiser
          </button>
        </div>
      )}
    </div>
      </main>
    </>
  )
}
