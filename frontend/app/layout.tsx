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
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#13161c' },
    { media: '(prefers-color-scheme: light)', color: '#f8f6f3' },
  ],
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
      <body className={`${inter.className} antialiased`} style={{ background: 'var(--bg)' }}>
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
