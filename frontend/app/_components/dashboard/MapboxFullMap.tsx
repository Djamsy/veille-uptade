'use client'

import { useState, useEffect, useRef } from 'react'
import { COMMUNE_COORDS } from '../../../lib/communes'

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || ''

type CommuneData = {
  stats: {
    total_items: number
    max_gravity: number
    article_count?: number
    transcription_count?: number
    affair_count?: number
  }
  affairs?: any[]
}

export function MapboxFullMap({
  communes,
  onSelectCommune,
}: {
  communes?: Record<string, CommuneData>
  onSelectCommune?: (name: string | null) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)
  const markersRef = useRef<any[]>([])
  const [ready, setReady] = useState(false)
  const [mapError, setMapError] = useState('')
  const initAttempted = useRef(false)

  useEffect(() => {
    if (typeof window === 'undefined' || initAttempted.current) return
    initAttempted.current = true

    const token = MAPBOX_TOKEN || (window as any).__MAPBOX_TOKEN || ''
    if (!token) {
      setMapError('Token Mapbox manquant')
      return
    }

    const initMap = () => {
      if (!containerRef.current || mapRef.current) return
      const mapboxgl = (window as any).mapboxgl
      if (!mapboxgl) { setMapError('Mapbox GL non chargé'); return }

      try {
        mapboxgl.accessToken = token
        const map = new mapboxgl.Map({
          container: containerRef.current,
          style: 'mapbox://styles/mapbox/satellite-streets-v12',
          center: [-61.55, 16.18],
          zoom: 10.2,
          pitch: 55,
          bearing: -15,
          antialias: true,
          attributionControl: false,
          failIfMajorPerformanceCaveat: false,
        })

        map.on('load', () => {
          setReady(true)
          try {
            map.addSource('mapbox-dem', {
              type: 'raster-dem', url: 'mapbox://mapbox.mapbox-terrain-dem-v1',
              tileSize: 512, maxzoom: 14,
            })
            map.setTerrain({ source: 'mapbox-dem', exaggeration: 1.8 })
            map.addLayer({
              id: 'sky', type: 'sky',
              paint: { 'sky-type': 'atmosphere', 'sky-atmosphere-sun': [0.0, 80.0], 'sky-atmosphere-sun-intensity': 15 },
            })
          } catch (e) { console.warn('[Map] Terrain/Sky error:', e) }
        })

        map.on('error', (e: any) => {
          console.error('[Map] Error:', e?.error?.message || e)
        })

        map.addControl(new mapboxgl.NavigationControl({ showCompass: true, visualizePitch: true }), 'bottom-right')
        mapRef.current = map
      } catch (e: any) {
        setMapError(e.message || 'Erreur init carte')
      }
    }

    const loadAndInit = () => {
      if ((window as any).mapboxgl) { initMap(); return }

      if (!document.querySelector('link[href*="mapbox-gl"]')) {
        const css = document.createElement('link')
        css.rel = 'stylesheet'
        css.href = 'https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.css'
        document.head.appendChild(css)
      }

      if (!document.querySelector('script[src*="mapbox-gl"]')) {
        const js = document.createElement('script')
        js.src = 'https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.js'
        js.async = true
        js.onload = () => { initMap() }
        js.onerror = () => { setMapError('CDN Mapbox inaccessible') }
        document.head.appendChild(js)
      } else {
        const check = setInterval(() => {
          if ((window as any).mapboxgl) { clearInterval(check); initMap() }
        }, 100)
        setTimeout(() => clearInterval(check), 10000)
      }
    }

    loadAndInit()
    return () => {
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null }
    }
  }, [])

  useEffect(() => {
    if (!mapRef.current || !communes || !ready) return
    const mapboxgl = (window as any).mapboxgl
    if (!mapboxgl) return

    markersRef.current.forEach(m => m.remove())
    markersRef.current = []

    for (const [name, cData] of Object.entries(communes)) {
      const coords = COMMUNE_COORDS[name]
      if (!coords || !cData.stats) continue
      const g = cData.stats.max_gravity
      const color = g >= 0.7 ? '#ef4444' : g >= 0.5 ? '#f97316' : g >= 0.3 ? '#eab308' : '#22c55e'
      const size = Math.min(44, Math.max(16, 10 + cData.stats.total_items * 2))

      const el = document.createElement('div')
      el.style.cssText = `width:${size}px;height:${size}px;cursor:pointer;background:radial-gradient(circle,${color}cc 0%,${color}44 50%,transparent 100%);border:2px solid ${color}aa;border-radius:50%;box-shadow:0 0 ${size * 1.5}px ${color}66;transition:transform 0.2s;`
      el.title = `${name} — ${cData.stats.total_items} items`
      el.onmouseenter = () => { el.style.transform = 'scale(1.3)' }
      el.onmouseleave = () => { el.style.transform = 'scale(1)' }

      const affairsList = (cData.affairs || []).slice(0, 3)
      const affairsHTML = affairsList.map((a: any) => {
        const gravityColor = (a.gravity_score || 0) >= 0.7 ? '#ef4444' : (a.gravity_score || 0) >= 0.5 ? '#f97316' : (a.gravity_score || 0) >= 0.3 ? '#eab308' : '#22c55e'
        return `<div style="padding:6px; border-bottom:1px solid rgba(255,255,255,0.08); font-size:11px;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px; margin-bottom:3px;">
            <span style="font-weight:600; color:#fff; flex:1;">${a.title || 'Sans titre'}</span>
            <span style="color:${gravityColor}; font-weight:700; flex-shrink:0;">${Math.round((a.gravity_score || 0) * 100)}%</span>
          </div>
          <div style="font-size:9px; color:rgba(255,255,255,0.6);">${a.theme || 'N/A'}</div>
        </div>`
      }).join('')

      const popupHTML = `
        <div style="background:rgba(2,6,23,0.92); backdrop-filter:blur(20px); border:1px solid rgba(255,255,255,0.1); border-radius:12px; color:#fff; font-family:system-ui,-apple-system,sans-serif; padding:0; min-width:240px; box-shadow:0 20px 25px -5px rgba(0,0,0,0.3);">
          <div style="padding:10px 12px; border-bottom:1px solid rgba(255,255,255,0.1);">
            <div style="font-weight:700; font-size:13px; margin-bottom:8px;">${name}</div>
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; text-align:center; font-size:11px;">
              <div>
                <div style="font-weight:700; color:#60a5fa; font-size:14px;">${cData.stats.article_count || 0}</div>
                <div style="color:rgba(255,255,255,0.5); font-size:9px; text-transform:uppercase;">Articles</div>
              </div>
              <div>
                <div style="font-weight:700; color:#a78bfa; font-size:14px;">${cData.stats.transcription_count || 0}</div>
                <div style="color:rgba(255,255,255,0.5); font-size:9px; text-transform:uppercase;">Radios</div>
              </div>
              <div>
                <div style="font-weight:700; color:#fbbf24; font-size:14px;">${cData.stats.affair_count || 0}</div>
                <div style="color:rgba(255,255,255,0.5); font-size:9px; text-transform:uppercase;">Affaires</div>
              </div>
            </div>
          </div>
          ${affairsHTML ? `<div style="max-height:180px; overflow-y:auto;">${affairsHTML}</div>` : `<div style="padding:10px 12px; color:rgba(255,255,255,0.4); font-size:11px;">Aucune affaire</div>`}
          <div style="padding:8px 12px; border-top:1px solid rgba(255,255,255,0.1); text-align:center;">
            <button style="background:rgba(99,102,241,0.5); color:#fff; border:none; padding:6px 12px; border-radius:6px; font-size:11px; font-weight:600; cursor:pointer; transition:background 0.2s;">Voir tout</button>
          </div>
        </div>
      `

      const popup = new mapboxgl.Popup({
        closeButton: true,
        closeOnClick: false,
        maxWidth: '280px',
      }).setHTML(popupHTML)

      el.onclick = () => {
        if (onSelectCommune) onSelectCommune(name)
        mapRef.current?.flyTo({ center: coords, zoom: 13, pitch: 60, duration: 1500 })
      }

      const marker = new mapboxgl.Marker({ element: el }).setLngLat(coords).setPopup(popup).addTo(mapRef.current)
      markersRef.current.push(marker)
    }
  }, [communes, ready, onSelectCommune])

  return (
    <>
      <div ref={containerRef} className="absolute inset-0" style={{ width: '100%', height: '100%' }} />
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center"
          style={{ background: 'radial-gradient(ellipse at 50% 55%, #0c1a30 0%, #020617 70%)' }}>
          <div className="text-center">
            <div className="w-16 h-16 rounded-full border-2 border-indigo-500/30 border-t-indigo-400 animate-spin mx-auto mb-4" />
            <p className="text-sm font-medium" style={{ color: 'rgba(255,255,255,0.5)' }}>
              {mapError ? mapError : 'Chargement de la carte 3D...'}
            </p>
            {mapError && (
              <p className="text-[10px] mt-2" style={{ color: 'rgba(255,255,255,0.25)' }}>
                Vérifiez NEXT_PUBLIC_MAPBOX_TOKEN dans Vercel
              </p>
            )}
          </div>
        </div>
      )}
    </>
  )
}
