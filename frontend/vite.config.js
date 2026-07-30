import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // This repo lives inside a cloud-synced folder (Dropbox); its real-time
  // sync agent intermittently locks Vite's dep-optimizer temp directory
  // right as Vite tries to rename it into place, causing a reproducible
  // EBUSY error on dev-server startup. Caching outside the synced tree
  // avoids that race entirely -- this is a local dev-server cache, not
  // build output, so it's fine for it to live outside the repo.
  cacheDir: join(tmpdir(), 'vite-launchino-frontend'),
})
