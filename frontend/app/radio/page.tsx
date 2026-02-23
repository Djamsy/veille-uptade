'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchRadioCardsToday,
  fetchRadioCards,
  captureRadioNow,
  refreshRadioSnapshot,
  fetchRadioDebugStreams,
  type RadioCard,
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
  if (!source) return 'bg-slate-100 text-slate-500'
  const s = source.toLowerCase()
  if (s.includes('rci')) return 'bg-amber-100 text-amber-600 border border-amber-200'
  if (s.includes('guadeloupe') || s.includes('gp')) return 'bg-blue-100 text-blue-600 border border-blue-200'
  return 'bg-purple-100 text-purple-600 border border-purple-200'
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
    <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5 animate-pulse">
      <div className="h-4 bg-slate-100 rounded w-3/4 mb-3" />
      <div className="h-3 bg-slate-200 rounded w-1/2 mb-4" />
      <div className="space-y-2">
        <div className="h-3 bg-slate-200 rounded w-full" />
        <div className="h-3 bg-slate-200 rounded w-5/6" />
        <div className="h-3 bg-slate-200 rounded w-2/3" />
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
    <div className="bg-white shadow-sm rounded-xl border border-slate-200 hover:border-slate-300 transition-colors">
      {/* Header */}
      <div className="px-5 pt-5 pb-3">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-slate-800 truncate">{card.title}</h3>
            <p className="text-xs text-slate-400 mt-0.5">{card.subtitle}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${sourceBadgeColor(card.source)}`}>
              {card.source || 'Radio'}
            </span>
            <span className="text-[10px] text-slate-400">{timeAgo(card.capturedAt)}</span>
          </div>
        </div>

        {/* Summary source badge */}
        <div className="flex items-center gap-2 mb-3">
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
            card.summarySource === 'gpt'
              ? 'bg-emerald-50 text-emerald-600'
              : 'bg-slate-100 text-slate-400'
          }`}>
            {summarySourceLabel(card.summarySource)}
          </span>
          {card.meta?.transcriptionMethod && (
            <span className="text-[10px] text-slate-500">
              {card.meta.transcriptionMethod}
            </span>
          )}
        </div>

        {/* Summary text */}
        <div className="text-sm text-slate-500 leading-relaxed">
          {expanded && card.fullText ? card.fullText : card.summary}
        </div>
        {card.isTruncated && (
          <button
            onClick={onToggle}
            className="mt-2 text-xs text-teal-600 hover:text-teal-500 transition-colors"
          >
            {expanded ? '▲ Réduire' : '▼ Voir tout'}
          </button>
        )}
      </div>

      {/* Audio player */}
      {card.audioUrl && (
        <div className="px-5 pb-4 pt-1 border-t border-slate-200">
          <audio
            controls
            preload="none"
            className="w-full h-8"
            style={{ opacity: 0.9 }}
          >
            <source src={`${BACKEND_URL}${card.audioUrl}`} type="audio/wav" />
          </audio>
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

  return (
    <>
      <Sidebar />
      <main className="ml-64 flex-1 p-8 min-h-screen">
      <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Transcriptions Radio</h1>
          <p className="text-sm text-slate-400 mt-1">
            {total} transcription{total !== 1 ? 's' : ''} • {viewMode === 'today' ? 'Aujourd\'hui' : selectedDate || '—'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Date toggle */}
          <div className="flex rounded-lg border border-slate-200 overflow-hidden">
            <button
              onClick={() => setViewMode('today')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === 'today'
                  ? 'bg-teal-100 text-teal-700'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Aujourd&apos;hui
            </button>
            <button
              onClick={() => setViewMode('date')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === 'date'
                  ? 'bg-teal-100 text-teal-700'
                  : 'text-slate-400 hover:text-slate-200'
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
              className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800"
            />
          )}

          <button
            onClick={handleRefreshSnapshot}
            disabled={refreshing}
            className="px-3 py-1.5 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg text-xs text-slate-500 transition-colors disabled:opacity-50"
          >
            {refreshing ? '⟳ Refresh...' : '⟳ Snapshot'}
          </button>

          <button
            onClick={() => setShowCapturePanel(!showCapturePanel)}
            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-xs text-slate-800 font-medium transition-colors"
          >
            🎙 Capturer
          </button>
        </div>
      </div>

      {/* Capture panel */}
      {showCapturePanel && (
        <div className="bg-white rounded-xl border border-emerald-200 p-5">
          <h3 className="text-sm font-semibold text-emerald-600 mb-3">Capture radio en direct</h3>
          <div className="flex items-end gap-3 flex-wrap">
            <div>
              <label className="block text-[10px] text-slate-400 mb-1">Flux / Section</label>
              <input
                type="text"
                value={captureSection}
                onChange={(e) => setCaptureSection(e.target.value)}
                placeholder="rci, guadeloupe, gp..."
                className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 placeholder-slate-400 w-48"
              />
            </div>
            <div>
              <label className="block text-[10px] text-slate-400 mb-1">Durée (sec)</label>
              <input
                type="number"
                value={captureDuration}
                onChange={(e) => setCaptureDuration(Number(e.target.value))}
                min={5}
                max={600}
                className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 w-24"
              />
            </div>
            <button
              onClick={handleCapture}
              disabled={capturing}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm text-slate-800 font-medium transition-colors disabled:opacity-50"
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
          <p className="mt-2 text-[10px] text-slate-400">
            Laissez le flux vide pour utiliser le stream prioritaire par défaut (RCI replay).
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg text-sm">
          {error}
          <button onClick={() => setError('')} className="ml-3 text-red-500 hover:text-red-400">✕</button>
        </div>
      )}

      {/* Cards grid */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[...Array(6)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : cards.length === 0 ? (
        <div className="bg-white/60 rounded-xl border border-slate-200 p-12 text-center">
          <div className="text-4xl mb-3">📻</div>
          <h3 className="text-lg font-medium text-slate-500 mb-1">Aucune transcription</h3>
          <p className="text-sm text-slate-400">
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
        <div className="flex items-center justify-between text-xs text-slate-400 px-1">
          <span>
            {cards.filter((c) => c.summarySource === 'gpt').length} résumés IA •{' '}
            {cards.filter((c) => c.audioUrl).length} avec audio
          </span>
          <button
            onClick={loadCards}
            className="text-teal-600 hover:text-teal-600 transition-colors"
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
