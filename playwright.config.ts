import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e',
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['./tests/reporters/testrail-reporter.ts'],
  ],
  use: {
    baseURL: process.env.MMFP_URL,
    httpCredentials:
      process.env.MMFP_BASIC_AUTH_USER && process.env.MMFP_BASIC_AUTH_PASS
        ? {
            username: process.env.MMFP_BASIC_AUTH_USER,
            password: process.env.MMFP_BASIC_AUTH_PASS,
          }
        : undefined,
  },
});
