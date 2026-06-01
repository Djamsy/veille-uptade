'use client'

/**
 * Page de rendu hors-écran du bilan hebdomadaire.
 *
 * Utilisée par le rendu serveur (Playwright) : on charge cette page dans un
 * navigateur headless, on attend que le PNG soit dessiné, puis on lit
 * `window.__REPORT_PNG__` (dataURL). Les données proviennent des endpoints
 * publics de l'observatoire — aucun token requis.
 *
 * URL : /report/render?days=7
 */

import { useEffect, useState } from 'react'
import {
  fetchWebHistory,
  fetchSocialEvolution,
  fetchDecisionInsights,
  fetchSocialHistory,
  type WebTrafficPoint,
  type SocialEvolution,
  type DecisionInsights as DecisionInsightsData,
  type AccountSnapshot,
} from '../../../lib/api'
import { renderWeeklyReportBlob } from '../../../lib/weeklyReport'

declare global {
  interface Window {
    __REPORT_PNG__?: string
    __REPORT_ERROR__?: string
  }
}

export default function ReportRenderPage() {
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    const days = Number(new URLSearchParams(window.location.search).get('days')) || 7

    ;(async () => {
      try {
        const [hist, evolution, insights, social] = await Promise.all([
          fetchWebHistory(90).catch(() => null),
          fetchSocialEvolution().catch(() => null),
          fetchDecisionInsights(days).catch(() => null),
          fetchSocialHistory(undefined, 30).catch(() => null),
        ])

        const points = hist?.points || []
        const web: WebTrafficPoint | null = hist?.latest || null
        const webPrev: WebTrafficPoint | null = points.length >= 2 ? points[points.length - 2] : null
        const history: Record<string, AccountSnapshot[]> = social?.series || {}

        const blob = await renderWeeklyReportBlob({
          web,
          webPrev,
          evolution: evolution as SocialEvolution | null,
          insights: insights as DecisionInsightsData | null,
          history,
        })
        if (!blob) throw new Error('blob null')

        const dataUrl: string = await new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onloadend = () => resolve(String(reader.result))
          reader.onerror = () => reject(new Error('read error'))
          reader.readAsDataURL(blob)
        })

        window.__REPORT_PNG__ = dataUrl
        setStatus('ready')
      } catch (e) {
        window.__REPORT_ERROR__ = String(e)
        setStatus('error')
      }
    })()
  }, [])

  // Marqueur lisible par Playwright (et utile au debug manuel).
  return <div id="report-status" data-status={status}>{status}</div>
}
