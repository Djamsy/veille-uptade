/** @type {import('next').NextConfig} */
const nextConfig = {
  // ── Performance ──
  compress: true,              // gzip automatique sur les réponses
  poweredByHeader: false,      // retire le header X-Powered-By
  reactStrictMode: false,      // évite double-render en dev (pas d'impact prod)

  // ── Optimisation images ──
  images: {
    formats: ['image/avif', 'image/webp'],
    minimumCacheTTL: 3600,     // cache images 1h
    deviceSizes: [375, 414, 640, 768, 1024, 1280],
  },

  // ── Bundle optimization ──
  experimental: {
    optimizePackageImports: ['recharts', 'lucide-react', '@heroicons/react', 'framer-motion', 'date-fns'],
  },

  // ── Proxy API vers le backend ──
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
      {
        source: '/health',
        destination: 'http://localhost:8000/health',
      },
    ];
  },

  // ── Cache headers pour les assets statiques ──
  async headers() {
    return [
      {
        source: '/_next/static/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
        ],
      },
      {
        source: '/api/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, s-maxage=30, stale-while-revalidate=60' },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
