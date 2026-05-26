/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-inter)', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['var(--font-newsreader)', 'Newsreader', 'Georgia', 'serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        // ── "Crème & encre" editorial palette ──
        // ── "Carte vivante" : échelle ink INVERSÉE pour le dark ──
        // (ink-900 = texte clair, ink-100 = hover translucide, ink-200 = bordure subtile)
        ink: {
          DEFAULT: '#EAF4F2',
          50:  'rgba(255,255,255,0.03)',
          100: 'rgba(255,255,255,0.06)',
          200: 'rgba(255,255,255,0.12)',
          300: '#56737a',
          400: '#6E8B92',
          500: '#8FB0B6',
          600: '#A7C4C9',
          700: '#c3dadd',
          800: '#dbeceb',
          900: '#EAF4F2',
        },
        // press = accent turquoise (CTA, focus rings)
        press: {
          DEFAULT: '#1FB6A6',
          dark: '#169B8D',
          light: '#2FD0BD',
        },
        alert: {
          DEFAULT: '#F0A93B',
          dark: '#E8743B',
          light: '#f6c06a',
          soft: 'rgba(240,169,59,0.14)',
        },
        link: {
          DEFAULT: '#5FD0E0',
          dark: '#1FB6A6',
          light: '#8fe0ec',
          soft: 'rgba(95,208,224,0.12)',
        },
        // ── Tokens topographie GPE (désaturés, lisibles sur clair) ──
        gpe: {
          green: '#4a7b56',  // mangrove
          yellow: '#b89030', // canne mûre
          red: '#a8324a',    // Soufrière
          blue: '#3e6fa3',
          coral: '#b8632a',
        },
        bmg: {
          low: '#4a7b56',      // mangrove
          medium: '#b89030',   // canne mûre
          high: '#8d4628',     // terre volcanique
          critical: '#a8324a', // Soufrière
        },
        sentiment: {
          positive: '#4a7b56',
          neutral: '#71717a',
          negative: '#a8324a',
        },
        // Soft backgrounds for tags
        'crit-soft': '#fdf2f4',
        'warn-soft': '#fdf6f0',
        'caution-soft': '#fdfaf0',
        'ok-soft': '#f0f8f1',
        'info-soft': '#f1f5fa',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.6s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'slide-in-left': 'slideInLeft 0.4s ease-out',
        'glow': 'glow 3s ease-in-out infinite alternate',
        'float': 'float 6s ease-in-out infinite',
        'shimmer-once': 'shimmerOnce 1.5s ease-out',
        'flag-slide': 'flagSlide 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInLeft: {
          '0%': { opacity: '0', transform: 'translateX(-16px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        glow: {
          '0%': { boxShadow: '0 0 20px rgba(37,99,235,0.08)' },
          '100%': { boxShadow: '0 0 50px rgba(37,99,235,0.15)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        shimmerOnce: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        flagSlide: {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      borderRadius: {
        '2xl': '16px',
        '3xl': '24px',
      },
    },
  },
  plugins: [],
}
