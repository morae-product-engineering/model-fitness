import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Mirror ui/tsconfig.json paths so tests can resolve @/* imports.
      '@': path.resolve(__dirname, 'ui'),
      // MLI-178: next is only installed in ui/node_modules; the root vitest
      // job can't resolve `next/server` when ui/middleware.ts is transitively
      // imported. Stub is in tests/stubs/next-server.ts.
      'next/server': path.resolve(__dirname, 'tests/stubs/next-server.ts'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    // Collect unit tests and tsx component tests; exclude e2e specs.
    include: ['tests/**/*.test.{ts,tsx}'],
  },
});
