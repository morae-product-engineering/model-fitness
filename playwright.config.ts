import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e',
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['./tests/reporters/testrail-reporter.ts'],
  ],
});
