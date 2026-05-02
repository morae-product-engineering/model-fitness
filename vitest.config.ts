import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Only collect unit tests; the Playwright `tests/e2e/*.spec.ts` files are
    // run via `npm run test:e2e` and use Playwright's own test runner.
    include: ['tests/**/*.test.ts'],
  },
});
