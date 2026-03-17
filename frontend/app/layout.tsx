import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'], weight: ['300', '400', '500', '600', '700'] })

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#050507' },
    { media: '(prefers-color-scheme: light)', color: '#6366f1' },
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
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    ],
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className={`${inter.className} antialiased`} style={{ background: '#050507' }}>
        {/* Ambient gradient background */}
        <div className="ambient-bg">
          <div className="ambient-orb-3" />
          <div className="noise-overlay" />
        </div>
        {/* Content */}
        <div className="relative z-10">
          {children}
        </div>
      </body>
    </html>
  )
}
