import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GitHub Pages serves at /Dexter/; Vercel and local dev serve at /.
// The Pages workflow sets VITE_BASE=/Dexter/ so both hosts work.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE ?? '/',
})
