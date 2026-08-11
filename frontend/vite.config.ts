import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_GH_PAGES=1 builds for GitHub Pages project-site hosting under /energy-tracker/
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_GH_PAGES ? '/energy-tracker/' : '/',
})
