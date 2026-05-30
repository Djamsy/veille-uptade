'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import type { Affair } from '../../../lib/api'
import { timeAgo } from '../../../lib/formatters'
import { ThemeBadge } from './ThemeBadge'

export function MajorStories({ affairs }: { affairs: Affair[] }) {
  const [idx, setIdx] = useState(0)
  const stories = affairs.slice(0, 5)

  useEffect(() => {
    if (stories.length <= 1) return
    const timer = setInterval(() => setIdx(i => (i + 1) % stories.length), 6000)
    return () => clearInterval(timer)
  }, [stories.length])

  if (stories.length === 0) {
    return <div className="text-center py-10 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune affaire majeure</div>
  }

  const affair = stories[idx]
  const priority = affair.priority || 'minor'
  const accentColor = priority === 'hot' ? '#f87171' : priority === 'watch' ? '#fbbf24' : '#34d399'

  return (
    <div className="relative">
      <Link href={`/affairs/${affair._id}`}>
        <div className="group cursor-pointer transition-all duration-500">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0 w-14 h-14 rounded-full border-2 border-cyan-500/40 flex items-center justify-center text-xs font-bold text-cyan-300">
              {Math.round((affair.bmg || 0) * 100)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                {priority === 'hot' && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold animate-pulse"
                    style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}>
                    URGENT
                  </span>
                )}
                <ThemeBadge theme={affair.theme} />
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{timeAgo(affair.last_activity || affair.created_at)}</span>
              </div>
              <h3 className="text-sm font-semibold text-white group-hover:text-blue-300 transition-colors line-clamp-2 mb-1.5">
                {affair.title || affair.primary_entity || 'Affaire'}
              </h3>
              {affair.description && (
                <p className="text-[11px] line-clamp-2 leading-relaxed" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  {affair.description}
                </p>
              )}
              <div className="flex items-center gap-3 mt-2">
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>
                  {affair.item_count || 0} sources
                </span>
                <span className="text-[10px] font-semibold" style={{ color: accentColor }}>
                  Gravité {Math.round((affair.gravity_score || 0) * 100)}%
                </span>
                {affair.sentiment && (
                  <span className="text-[10px] capitalize" style={{
                    color: affair.sentiment === 'positif' ? '#34d399' : affair.sentiment === 'négatif' ? '#f87171' : '#5FD0E0'
                  }}>{affair.sentiment}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </Link>

      {stories.length > 1 && (
        <div className="flex items-center justify-center gap-1.5 mt-4">
          {stories.map((_, i) => (
            <button key={i} onClick={() => setIdx(i)}
              className="transition-all duration-300"
              style={{
                width: i === idx ? 16 : 6,
                height: 6,
                borderRadius: 3,
                background: i === idx ? accentColor : 'rgba(255,255,255,0.1)',
                boxShadow: i === idx ? `0 0 8px ${accentColor}40` : 'none',
              }} />
          ))}
        </div>
      )}
    </div>
  )
}
