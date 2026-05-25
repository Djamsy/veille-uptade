import Link from 'next/link'
import { GuadeloupeMark } from '../components/GuadeloupeMark'

export default function NotFound() {
  return (
    <main
      className="relative min-h-screen flex flex-col items-center justify-center px-6 overflow-hidden"
      style={{ background: 'var(--bg-base)', color: 'var(--text)' }}
    >
      {/* Signature — silhouette du papillon en filigrane */}
      <GuadeloupeMark
        className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[520px] max-w-[90vw] h-auto"
        stroke="#18181b"
        style={{ opacity: 0.04 }}
      />

      <div className="relative max-w-xl text-center">
        <div
          className="font-mono text-[11px] uppercase tracking-[0.2em] reveal reveal-1"
          style={{ color: 'var(--text-muted)' }}
        >
          Erreur 404 · 971
        </div>

        <h1
          className="masthead text-5xl sm:text-6xl lg:text-7xl font-medium mt-4 reveal reveal-2"
          style={{ color: 'var(--text)' }}
        >
          Page introuvable
        </h1>

        {/* Drapeau GP éditorialisé — marqueur d'identité */}
        <div className="flag-stripe w-20 mx-auto mt-6 reveal reveal-2" />

        <p
          className="font-serif text-base sm:text-lg italic leading-relaxed mt-6 reveal reveal-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Cette page a peut-être été déplacée, archivée, ou n&rsquo;a jamais
          existé. Le fil de la veille, lui, continue.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3 mt-8 reveal reveal-3">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-sm transition-colors"
            style={{ background: 'var(--accent-press)', color: '#fafafa', border: '1px solid var(--accent-press)' }}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
            Retour au pilotage
          </Link>
          <Link
            href="/briefing"
            className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-sm transition-colors hover:bg-ink-100"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            Voir le briefing du jour
          </Link>
        </div>
      </div>
    </main>
  )
}
