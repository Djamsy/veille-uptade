'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import { type Affair } from '../../lib/api'

const API = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

interface ElectionAffair extends Affair {
  communes?: string[]
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return "à l'instant"
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

function sentimentEmoji(s: string): string {
  if (!s || s === 'neutre') return ''
  if (s.includes('négatif') || s.includes('negatif') || s === 'critique') return '😠'
  if (s.includes('positif')) return '😊'
  return '😐'
}

function sentimentColor(s: string): string {
  if (!s || s === 'neutre') return 'rgba(255,255,255,0.35)'
  if (s.includes('négatif') || s.includes('negatif') || s === 'critique') return '#f87171'
  if (s.includes('positif')) return '#6ee7b7'
  return '#fbbf24'
}

export default function ElectionsPage() {
  const [elections, setElections] = useState<ElectionAffair[]>([])
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/affairs/elections`).then(r => r.json())
      setElections(res.affairs || [])
    } catch (e) {
      console.error('Elections load error:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-main)' }}>
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Elections Municipales 2026
            </h1>
            <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
              Suivi des affaires liées aux élections municipales en Guadeloupe
            </p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
            </div>
          ) : elections.length === 0 ? (
            <div className="glass-card border border-[rgba(255,255,255,0.08)] p-10 text-center">
              <p className="text-sm" style={{ color: 'rgba(255,255,255,0.35)' }}>
                Aucune affaire électorale détectée pour le moment.
              </p>
              <p className="text-xs mt-2" style={{ color: 'rgba(255,255,255,0.2)' }}>
                Les articles mentionnant les municipales 2026 créeront automatiquement des affaires.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {elections.map((affair) => (
                <Link key={affair._id} href={`/affairs/${affair._id}`}>
                  <div className="glass-card border border-[rgba(255,255,255,0.08)] p-5 cursor-pointer hover:border-[rgba(255,255,255,0.15)] transition-all h-full">
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <h3 className="text-sm font-semibold text-white line-clamp-2 flex-1">
                        {affair.title}
                      </h3>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold flex-shrink-0 ${
                        affair.gravity_score >= 0.7 ? 'bg-red-500/20 text-red-400'
                        : affair.gravity_score >= 0.5 ? 'bg-orange-500/20 text-orange-400'
                        : 'bg-emerald-500/20 text-emerald-400'
                      }`}>
                        {Math.round(affair.gravity_score * 100)}%
                      </span>
                    </div>

                    {affair.description && (
                      <p className="text-[10px] line-clamp-3 mb-3" style={{ color: 'rgba(255,255,255,0.4)' }}>
                        {affair.description}
                      </p>
                    )}

                    <div className="flex items-center gap-2 flex-wrap">
                      {affair.communes && affair.communes.slice(0, 3).map((c) => (
                        <span key={c} className="text-[9px] px-1.5 py-0.5 rounded-full"
                          style={{
                            background: 'rgba(37,99,235,0.15)',
                            color: '#a5b4fc',
                            border: '1px solid rgba(37,99,235,0.3)',
                          }}>
                          {c}
                        </span>
                      ))}
                      {affair.sentiment && affair.sentiment !== 'neutre' && (
                        <span className="text-[9px]" style={{ color: sentimentColor(affair.sentiment) }}>
                          {sentimentEmoji(affair.sentiment)} {affair.sentiment}
                        </span>
                      )}
                      <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                        {affair.item_count} items · {timeAgo(affair.last_activity || affair.created_at)}
                      </span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
