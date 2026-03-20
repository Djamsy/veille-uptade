'use client'

import Link from 'next/link'

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'linear-gradient(180deg, #060a13 0%, #0a1628 50%, #060a13 100%)' }}>
      {/* Header */}
      <header className="flex items-center justify-between px-6 lg:px-12 py-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, #16a34a 0%, #2563eb 50%, #eab308 100%)',
              boxShadow: '0 4px 20px rgba(37,99,235,0.3)',
            }}>
            <span className="text-sm font-black text-white tracking-tighter">VM</span>
          </div>
          <div>
            <h1 className="text-sm font-bold text-white leading-tight">Veille Média</h1>
            <p className="text-[10px] font-bold tracking-[0.15em] uppercase"
              style={{ background: 'linear-gradient(90deg, #16a34a, #eab308)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Guadeloupe 971
            </p>
          </div>
        </div>
        <Link href="/auth/login"
          className="px-5 py-2 text-sm font-medium text-white rounded-xl transition-all hover:scale-105"
          style={{ background: 'rgba(37,99,235,0.15)', border: '1px solid rgba(37,99,235,0.25)' }}>
          Se connecter
        </Link>
      </header>

      {/* Hero */}
      <main className="flex-1 flex items-center justify-center px-6">
        <div className="max-w-3xl text-center">
          {/* Decorative glow */}
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 rounded-full opacity-20 blur-3xl pointer-events-none"
            style={{ background: 'radial-gradient(circle, rgba(37,99,235,0.4) 0%, transparent 70%)' }} />

          <div className="relative">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium mb-8"
              style={{ background: 'rgba(22,163,74,0.1)', border: '1px solid rgba(22,163,74,0.2)', color: '#34d399' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Surveillance en temps réel
            </div>

            <h2 className="text-3xl lg:text-5xl font-bold text-white leading-tight mb-6 tracking-tight">
              L'intelligence média<br />
              <span style={{ background: 'linear-gradient(90deg, #16a34a, #2563eb, #eab308)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                au service de la Guadeloupe
              </span>
            </h2>

            <p className="text-base lg:text-lg mb-10 max-w-xl mx-auto" style={{ color: 'rgba(255,255,255,0.4)' }}>
              Plateforme de veille médiatique automatisée. Articles, radio, réseaux sociaux — analysés, corrélés et scorés par intelligence artificielle.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/auth/login"
                className="px-8 py-3 text-sm font-semibold text-white rounded-xl transition-all hover:scale-105 hover:shadow-lg"
                style={{
                  background: 'linear-gradient(135deg, #2563eb, #16a34a)',
                  boxShadow: '0 4px 20px rgba(37,99,235,0.3)',
                }}>
                Accéder à la plateforme
              </Link>
              <Link href="/auth/register"
                className="px-8 py-3 text-sm font-medium text-white/60 rounded-xl transition-all hover:text-white hover:bg-white/5"
                style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
                Créer un compte
              </Link>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-16 max-w-2xl mx-auto">
            {[
              { label: 'Sources surveillées', value: '15+' },
              { label: 'Articles/jour', value: '100+' },
              { label: 'Radios live', value: '6' },
              { label: 'Réseaux sociaux', value: '3' },
            ].map((stat, i) => (
              <div key={i} className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
                <p className="text-xl font-bold text-white">{stat.value}</p>
                <p className="text-[10px] text-white/30 uppercase tracking-wider mt-1">{stat.label}</p>
              </div>
            ))}
          </div>

          {/* Features */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-12 max-w-3xl mx-auto text-left">
            {[
              {
                title: 'Détection automatique',
                desc: 'Les affaires sont identifiées et regroupées automatiquement par clustering IA.',
                color: '#f87171',
              },
              {
                title: 'Bruit Média (BMG)',
                desc: 'Score de bruit numérique calculé en temps réel sur tous les canaux.',
                color: '#fbbf24',
              },
              {
                title: 'Analyse prédictive',
                desc: 'Anticipez les tendances et les crises grâce à l\'IA prédictive GPT.',
                color: '#34d399',
              },
            ].map((feat, i) => (
              <div key={i} className="p-5 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
                <div className="w-2 h-2 rounded-full mb-3" style={{ backgroundColor: feat.color, boxShadow: `0 0 8px ${feat.color}40` }} />
                <h3 className="text-sm font-semibold text-white mb-1">{feat.title}</h3>
                <p className="text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>{feat.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="py-6 text-center">
        <p className="text-[10px] text-white/20">
          Veille Média Guadeloupe — Surveillance automatisée du paysage médiatique guadeloupéen
        </p>
      </footer>
    </div>
  )
}
