'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  fetchSocialStats,
  fetchSocialPosts,
  fetchSocialScrapeAll,
  fetchSocialConfig,
  SocialPost,
  SocialStats,
} from '../../lib/api';

const PLATFORM_CONFIG: Record<string, { icon: string; label: string; color: string; bg: string }> = {
  facebook: { icon: '📘', label: 'Facebook', color: '#1877f2', bg: 'rgba(24,119,242,0.1)' },
  instagram: { icon: '📸', label: 'Instagram', color: '#e4405f', bg: 'rgba(228,64,95,0.1)' },
  twitter: { icon: '🐦', label: 'Twitter / X', color: '#1da1f2', bg: 'rgba(29,161,242,0.1)' },
};

export default function SocialPage() {
  const [stats, setStats] = useState<SocialStats | null>(null);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [activePlatform, setActivePlatform] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [scraping, setScraping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [s, p, c] = await Promise.all([
        fetchSocialStats(),
        fetchSocialPosts(activePlatform, 50),
        fetchSocialConfig(),
      ]);
      setStats(s);
      setPosts(p.posts);
      setConfig(c);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur de chargement');
    } finally {
      setLoading(false);
    }
  }, [activePlatform]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleScrape = async () => {
    setScraping(true);
    try {
      await fetchSocialScrapeAll();
      await loadData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur scraping');
    } finally {
      setScraping(false);
    }
  };

  const apifyConfigured = config && (config as Record<string, unknown>).apify_configured;

  return (
    <div style={{ minHeight: '100vh', background: '#0a0e1a', color: '#e2e8f0', padding: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, color: '#f1f5f9' }}>
            📱 Réseaux Sociaux
          </h1>
          <p style={{ margin: '4px 0 0', color: '#94a3b8', fontSize: 14 }}>
            Veille Facebook, Instagram & Twitter/X via Apify
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={loadData}
            disabled={loading}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid #334155',
              background: '#1e293b', color: '#e2e8f0', cursor: 'pointer', fontSize: 13,
            }}
          >
            ↻ Rafraîchir
          </button>
          <button
            onClick={handleScrape}
            disabled={scraping || !apifyConfigured}
            style={{
              padding: '8px 16px', borderRadius: 8, border: 'none',
              background: apifyConfigured ? '#6366f1' : '#334155',
              color: '#fff', cursor: apifyConfigured ? 'pointer' : 'not-allowed',
              fontSize: 13, fontWeight: 600,
            }}
          >
            {scraping ? '⏳ Scraping...' : '🚀 Lancer scraping'}
          </button>
        </div>
      </div>

      {!apifyConfigured && (
        <div style={{
          padding: 16, borderRadius: 12, background: 'rgba(251,191,36,0.1)',
          border: '1px solid rgba(251,191,36,0.3)', marginBottom: 20, fontSize: 14,
        }}>
          ⚠️ <strong>APIFY_TOKEN non configuré.</strong> Ajoutez la variable d&apos;environnement APIFY_TOKEN
          dans Render pour activer le scraping automatique des réseaux sociaux.
        </div>
      )}

      {error && (
        <div style={{
          padding: 12, borderRadius: 8, background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)', marginBottom: 16, fontSize: 13, color: '#fca5a5',
        }}>
          ❌ {error}
        </div>
      )}

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {Object.entries(PLATFORM_CONFIG).map(([key, cfg]) => {
          const platStats = stats?.stats?.[key];
          return (
            <div
              key={key}
              onClick={() => setActivePlatform(activePlatform === key ? undefined : key)}
              style={{
                padding: 20, borderRadius: 16, cursor: 'pointer',
                background: activePlatform === key ? cfg.bg : '#111827',
                border: `1px solid ${activePlatform === key ? cfg.color : '#1e293b'}`,
                transition: 'all 0.2s',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 28 }}>{cfg.icon}</span>
                <span style={{
                  fontSize: 11, padding: '2px 8px', borderRadius: 6,
                  background: platStats?.last_24h ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                  color: platStats?.last_24h ? '#4ade80' : '#f87171',
                }}>
                  {platStats?.last_24h ? `${platStats.last_24h} nouveaux` : 'Aucun'}
                </span>
              </div>
              <h3 style={{ margin: '12px 0 4px', fontSize: 16, fontWeight: 600, color: '#f1f5f9' }}>
                {cfg.label}
              </h3>
              <div style={{ display: 'flex', gap: 16, fontSize: 13, color: '#94a3b8' }}>
                <span>24h: <strong style={{ color: '#e2e8f0' }}>{platStats?.last_24h || 0}</strong></span>
                <span>7j: <strong style={{ color: '#e2e8f0' }}>{platStats?.last_7d || 0}</strong></span>
                <span>Total: <strong style={{ color: '#e2e8f0' }}>{platStats?.total || 0}</strong></span>
              </div>
              {platStats?.last_scraped && (
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 8 }}>
                  Dernier scrape: {new Date(platStats.last_scraped).toLocaleString('fr-FR')}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setActivePlatform(undefined)}
          style={{
            padding: '6px 14px', borderRadius: 8, fontSize: 13, cursor: 'pointer',
            background: !activePlatform ? '#6366f1' : '#1e293b',
            color: !activePlatform ? '#fff' : '#94a3b8',
            border: 'none',
          }}
        >
          Tous
        </button>
        {Object.entries(PLATFORM_CONFIG).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => setActivePlatform(activePlatform === key ? undefined : key)}
            style={{
              padding: '6px 14px', borderRadius: 8, fontSize: 13, cursor: 'pointer',
              background: activePlatform === key ? cfg.color : '#1e293b',
              color: activePlatform === key ? '#fff' : '#94a3b8',
              border: 'none',
            }}
          >
            {cfg.icon} {cfg.label}
          </button>
        ))}
      </div>

      {/* Posts Feed */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>⏳ Chargement...</div>
        ) : posts.length === 0 ? (
          <div style={{
            textAlign: 'center', padding: 60, color: '#64748b',
            background: '#111827', borderRadius: 16, border: '1px solid #1e293b',
          }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📱</div>
            <p style={{ fontSize: 16 }}>Aucun post récupéré</p>
            <p style={{ fontSize: 13 }}>
              {apifyConfigured
                ? 'Lancez un scraping pour récupérer les posts des réseaux sociaux.'
                : 'Configurez APIFY_TOKEN dans Render pour activer le scraping.'}
            </p>
          </div>
        ) : (
          posts.map((post) => {
            const cfg = PLATFORM_CONFIG[post.platform] || PLATFORM_CONFIG.twitter;
            return (
              <div
                key={post._id}
                style={{
                  padding: 16, borderRadius: 12, background: '#111827',
                  border: '1px solid #1e293b', transition: 'border-color 0.2s',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <span style={{
                      fontSize: 11, padding: '2px 8px', borderRadius: 6,
                      background: cfg.bg, color: cfg.color, fontWeight: 600,
                    }}>
                      {cfg.icon} {cfg.label}
                    </span>
                    <span style={{ fontWeight: 600, color: '#f1f5f9', fontSize: 14 }}>
                      @{post.author}
                    </span>
                  </div>
                  <span style={{ fontSize: 11, color: '#64748b' }}>
                    {post.scraped_at ? new Date(post.scraped_at).toLocaleString('fr-FR') : ''}
                  </span>
                </div>
                <p style={{ margin: '10px 0', fontSize: 14, color: '#cbd5e1', lineHeight: 1.5 }}>
                  {post.text?.slice(0, 300)}{post.text?.length > 300 ? '...' : ''}
                </p>
                <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#64748b' }}>
                  <span>❤️ {post.likes || 0}</span>
                  {post.comments !== undefined && <span>💬 {post.comments}</span>}
                  {post.shares !== undefined && <span>🔄 {post.shares}</span>}
                  {post.retweets !== undefined && <span>🔁 {post.retweets}</span>}
                  {post.url && (
                    <a
                      href={post.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: '#6366f1', textDecoration: 'none' }}
                    >
                      ↗ Voir le post
                    </a>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
