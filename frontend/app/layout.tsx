import type { Metadata, Viewport } from 'next'
import { Inter, Newsreader, Space_Grotesk, IBM_Plex_Mono } from 'next/font/google'
import './globals.css'
import ClientLayout from '../components/ClientLayout'
import ServiceWorkerRegistration from '../components/ServiceWorkerRegistration'

const inter = Inter({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-inter',
  display: 'swap',
})

const newsreader = Newsreader({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-newsreader',
  display: 'swap',
})

// ── Thème « Carte vivante » : grotesk UI + mono data ──
const grotesk = Space_Grotesk({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-grotesk',
  display: 'swap',
})

const plexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono-data',
  display: 'swap',
})

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  themeColor: '#fafafa',
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
    <html lang="fr" className={`${inter.variable} ${newsreader.variable} ${grotesk.variable} ${plexMono.variable}`}>
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
      <body className="font-sans antialiased" style={{ background: '#fafafa', color: '#18181b' }}>
        <ServiceWorkerRegistration />
        <ClientLayout>{children}</ClientLayout>
      </body>
    </html>
  )
}
