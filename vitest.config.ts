import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Mirror ui/tsconfig.json paths so tests can resolve @/* imports.
      '@': path.resolve(__dirname, 'ui'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    // Collect unit tests and tsx component tests; exclude e2e specs.
    include: ['tests/**/*.test.{ts,tsx}'],
  },
});
