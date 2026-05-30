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
          scrollZoom: false, // le scroll de la page ne zoome plus la carte
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
      el.style.cssText = `width:${size}px;height:${size}px;cursor:pointer;`
      // Le cercle visuel est un ENFANT : on ne touche jamais au transform de `el`
      // (Mapbox y stocke le translate de position → sinon le marqueur saute au survol).
      const dot = document.createElement('div')
      dot.style.cssText = `width:100%;height:100%;color:${color};background:radial-gradient(circle,${color}cc 0%,${color}44 50%,transparent 100%);border:2px solid ${color}aa;border-radius:50%;box-shadow:0 0 ${size * 1.5}px ${color}66;transition:transform 0.2s;`
      // Marqueur vivant : pulse pour les communes à gravité élevée
      if (g >= 0.5) dot.classList.add('marker-pulse')
      el.appendChild(dot)
      el.title = `${name} — ${cData.stats.total_items} items`
      el.onmouseenter = () => { dot.style.transform = 'scale(1.3)' }
      el.onmouseleave = () => { dot.style.transform = 'scale(1)' }

      // Pas de popup sur la carte (buggé/encombrant) : le détail vit sur la page 2.
      // Clic sur un marqueur = zoom doux sur la commune + notifie le parent.
      el.onclick = () => {
        if (onSelectCommune) onSelectCommune(name)
        mapRef.current?.flyTo({ center: coords, zoom: 12.5, pitch: 55, duration: 1400 })
      }

      const marker = new mapboxgl.Marker({ element: el }).setLngLat(coords).addTo(mapRef.current)
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
