/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    appDir: true,
  },
  env: {
    BACKEND_URL: process.env.BACKEND_URL || 'http://localhost:8000',
    WS_URL: process.env.WS_URL || 'ws://localhost:8000/ws',
  },
  images: {
    domains: [
      'www.franceantilles.fr', 
      'www.rci.fm', 
      'www.karibinfo.com',
      'la1ere.francetvinfo.fr'
    ],
  },
  rewrites: async () => [
    {
      source: '/api/:path*',
      destination: `${process.env.BACKEND_URL || 'http://localhost:8000'}/api/:path*`,
    },
  ],
}

module.exports = nextConfig