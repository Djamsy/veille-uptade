import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import ClientLayout from '../components/ClientLayout'
import ServiceWorkerRegistration from '../components/ServiceWorkerRegistration'

const inter = Inter({ subsets: ['latin'], weight: ['300', '400', '500', '600', '700'] })

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  themeColor: '#0a0a0f',
}

export const metadata: Metadata = {
  title: 'Veille Média Guadeloupe',
  description: 'Plateforme de veille médiatique intelligente — Suivi des affaires, BMG et sentiment',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Veille Média',
  },
  icons: {
    icon: [
      { url: '/icons/icon-192.svg', sizes: '192x192', type: 'image/svg+xml' },
      { url: '/icons/icon-512.svg', sizes: '512x512', type: 'image/svg+xml' },
    ],
    apple: [
      { url: '/icons/icon-192.svg', sizes: '192x192', type: 'image/svg+xml' },
    ],
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <head>
        {/* Preconnect Mapbox CDN — réduit la latence de 200-500ms */}
        <link rel="preconnect" href="https://api.mapbox.com" />
        <link rel="preconnect" href="https://events.mapbox.com" />
        <link rel="dns-prefetch" href="https://api.mapbox.com" />
        {/* Preload Mapbox CSS (critique pour le rendu de la carte) */}
        <link
          rel="preload"
          href="https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.css"
          as="style"
        />
        <link
          rel="stylesheet"
          href="https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.css"
        />
      </head>
      <body className={`${inter.className} antialiased`} style={{ background: '#0a0a0f', color: '#f1f5f9' }}>
        <ServiceWorkerRegistration />
        {/* Ambient gradient background */}
        <div className="ambient-bg">
          <div className="ambient-orb-3" />
          <div className="noise-overlay" />
        </div>
        {/* Content */}
        <div className="relative z-10">
          <ClientLayout>{children}</ClientLayout>
        </div>
      </body>
    </html>
  )
}
