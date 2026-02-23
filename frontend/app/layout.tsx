import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Veille Média Guadeloupe',
  description: 'Plateforme de veille médiatique intelligente — Suivi des affaires, BMG et sentiment',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className="dark">
      <body className={`${inter.className} antialiased`}>{children}</body>
    </html>
  )
}
