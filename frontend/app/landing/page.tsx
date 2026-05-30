'use client'

import Link from 'next/link'

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-base)' }}>
      <header
        className="flex items-center justify-between px-6 lg:px-12 py-5"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-md flex items-center justify-center"
            style={{ background: 'var(--brand-gradient)' }}
          >
            <span className="font-serif text-sm font-semibold text-white">VM</span>
          </div>
          <div>
            <h1 className="font-serif text-base font-semibold leading-tight tracking-tight" style={{ color: 'var(--text)' }}>
              Veille Média
            </h1>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-muted)' }}>
              Guadeloupe · 971
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/auth/login"
            className="px-4 py-1.5 text-xs font-semibold rounded-sm transition-colors"
            style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}
          >
            Se connecter
          </Link>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="max-w-3xl text-center">
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full font-mono text-[10px] uppercase tracking-[0.14em] mb-8"
            style={{ background: 'var(--ok-soft)', color: '#3d6f44', border: '1px solid #cce5d0' }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--positive)' }} />
            Surveillance en temps réel
          </div>

          <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--text-muted)' }}>
            Présentation / Plateforme
          </div>
          <h2
            className="font-serif text-4xl lg:text-6xl font-medium tracking-tight italic leading-[1.05] mb-6"
            style={{ color: 'var(--text)' }}
          >
            L&rsquo;intelligence média
            <br />
            au service de la Guadeloupe
          </h2>

          <p
            className="text-base lg:text-lg mb-10 max-w-xl mx-auto leading-relaxed"
            style={{ color: 'var(--text-secondary)' }}
          >
            Plateforme de veille médiatique automatisée. Articles, radio, réseaux sociaux —
            analysés, corrélés et scorés par intelligence artificielle.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-16">
            <Link
              href="/auth/login"
              className="px-6 py-2.5 text-sm font-semibold rounded-sm transition-colors"
              style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}
            >
              Accéder à la plateforme
            </Link>
            <Link
              href="/auth/register"
              className="px-6 py-2.5 text-sm font-medium rounded-sm transition-colors hover:bg-ink-100"
              style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            >
              Créer un compte
            </Link>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-2xl mx-auto mb-12">
            {[
              { label: 'Sources surveillées', value: '15+' },
              { label: 'Articles / jour', value: '100+' },
              { label: 'Radios live', value: '6' },
              { label: 'Réseaux sociaux', value: '3' },
            ].map(stat => (
              <div
                key={stat.label}
                className="p-4 text-left"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
              >
                <p className="font-serif text-2xl font-semibold tabular-nums" style={{ color: 'var(--text)' }}>
                  {stat.value}
                </p>
                <p
                  className="font-mono text-[9px] uppercase tracking-[0.14em] mt-1"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {stat.label}
                </p>
              </div>
            ))}
          </div>

          {/* Features */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-3xl mx-auto text-left">
            {[
              {
                title: 'Détection automatique',
                desc: 'Les affaires sont identifiées et regroupées automatiquement par clustering IA.',
                color: 'var(--negative)',
              },
              {
                title: 'Bruit Média (BMG)',
                desc: 'Score de bruit numérique calculé en temps réel sur tous les canaux.',
                color: 'var(--warning)',
              },
              {
                title: 'Analyse prédictive',
                desc: "Anticipez les tendances et les crises grâce à l'IA prédictive.",
                color: 'var(--positive)',
              },
            ].map(feat => (
              <div
                key={feat.title}
                className="p-5"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
              >
                <div className="w-2 h-2 rounded-full mb-3" style={{ background: feat.color }} />
                <h3 className="font-serif text-base font-semibold tracking-tight mb-1" style={{ color: 'var(--text)' }}>
                  {feat.title}
                </h3>
                <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                  {feat.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </main>

      <footer className="py-6 text-center" style={{ borderTop: '1px solid var(--border)' }}>
        <p className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
          Veille Média Guadeloupe — Surveillance automatisée du paysage médiatique guadeloupéen
        </p>
      </footer>
    </div>
  )
}
