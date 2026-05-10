import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Ensure DOM is cleaned up between tests. RTL auto-cleanup only fires when
// the module is imported in a beforeEach/afterEach context; explicit call
// here guarantees it regardless of the test runner setup.
afterEach(() => {
  cleanup();
});
