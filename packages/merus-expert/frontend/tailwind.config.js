/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          50: '#f0f1f5',
          100: '#d9dce6',
          200: '#b3b9cd',
          300: '#8d96b4',
          400: '#67739b',
          500: '#415082',
          600: '#344068',
          700: '#27304e',
          800: '#1A2849',
          900: '#0d1424',
        },
        teal: {
          50: '#e6f5f5',
          100: '#b3e0e0',
          200: '#80cbcb',
          300: '#4db6b6',
          400: '#1aa1a1',
          500: '#0D7C7D',
          600: '#0a6364',
          700: '#084a4b',
          800: '#053132',
          900: '#031919',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
