/** @type {import('tailwindcss').Config} */
export default {
  content: ['./renderer/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          0: '#0a0a0f',
          1: '#0f0f17',
          2: '#15151f',
          3: '#1c1c28',
          4: '#242433',
        },
        border: {
          subtle: '#ffffff08',
          default: '#ffffff12',
          strong: '#ffffff20',
        },
        accent: {
          blue: '#3b82f6',
          cyan: '#06b6d4',
          green: '#10b981',
          amber: '#f59e0b',
          red: '#ef4444',
          purple: '#8b5cf6',
        },
        text: {
          primary: '#f0f0f8',
          secondary: '#9090a8',
          muted: '#50506a',
        }
      },
      fontFamily: {
        sans: ['Inter Variable', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        display: ['Cal Sans', 'Inter Variable', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-in-right': 'slideInRight 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        }
      }
    }
  },
  plugins: [require('@tailwindcss/forms')]
}
