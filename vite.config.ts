import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base matches the GitHub Pages project path: https://xd-olayinka.github.io/Dexter/
export default defineConfig({
  plugins: [react()],
  base: '/Dexter/',
})
