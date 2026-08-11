import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_BASE is set by the Pages deploy workflow from actions/configure-pages —
// "/energlens/" for a project site, "/" behind a custom domain. Defaults to "/"
// for local dev and for the plain CI build.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || '/',
})
