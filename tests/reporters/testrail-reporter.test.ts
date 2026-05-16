import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import * as fs from 'fs';
import TestRailReporter from './testrail-reporter';

// Mock fs at the module level so the reporter's `import * as fs from 'fs'`
// receives our spies. vi.spyOn on the live namespace fails in ESM because
// the re-exports are non-configurable.
vi.mock('fs', async () => {
  const actual = await vi.importActual<typeof import('fs')>('fs');
  return {
    ...actual,
    writeFileSync: vi.fn(),
    readFileSync: vi.fn(),
  };
});

// Minimal fakes that satisfy the bits of the Playwright Reporter API
// the reporter actually touches. Avoids importing types at runtime.

interface FakeTest {
  title: string;
  retries: number;
  location: { file: string; line: number; column: number };
}

interface FakeResult {
  status: 'passed' | 'failed' | 'timedOut' | 'skipped' | 'interrupted';
  duration: number;
  retry: number;
  errors: Array<{ message?: string; stack?: string }>;
  error?: { message?: string; stack?: string };
}

function makeTest(overrides: Partial<FakeTest> = {}): FakeTest {
  return {
    title: 'walking skeleton: scorecard page displays hardcoded score',
    retries: 0,
    location: {
      file: '/repo/tests/e2e/slice-01-walking-skeleton.spec.ts',
      line: 4,
      column: 1,
    },
    ...overrides,
  };
}

function makeResult(overrides: Partial<FakeResult> = {}): FakeResult {
  return {
    status: 'passed',
    duration: 1234,
    retry: 0,
    errors: [],
    ...overrides,
  };
}

function makeSuite(tests: FakeTest[]): { allTests: () => FakeTest[] } {
  return { allTests: () => tests };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const ENV = {
  TESTRAIL_URL: 'https://example.testrail.io',
  TESTRAIL_USER: 'user@example.com',
  TESTRAIL_API_KEY: 'fake-key',
  TESTRAIL_PROJECT_ID: '42',
  TESTRAIL_SUITE_SLICE_01: '7',
};

let fetchMock: ReturnType<typeof vi.fn>;
let warnSpy: ReturnType<typeof vi.spyOn>;
let errorSpy: ReturnType<typeof vi.spyOn>;
const writeFileMock = fs.writeFileSync as unknown as Mock;
const readFileMock = fs.readFileSync as unknown as Mock;

beforeEach(() => {
  for (const [k, v] of Object.entries(ENV)) {
    vi.stubEnv(k, v);
  }
  vi.stubEnv('GITHUB_RUN_ID', '12345');
  vi.stubEnv('GITHUB_REF_NAME', 'slice-01/testrail-reporter');
  vi.stubEnv('GITHUB_SHA', 'deadbeef');
  vi.stubEnv('GITHUB_REPOSITORY', 'morae-product-engineering/model-fitness');
  vi.stubEnv('GITHUB_SERVER_URL', 'https://github.com');

  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);

  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

  writeFileMock.mockReset();
  readFileMock.mockReset();
  readFileMock.mockReturnValue('// @jira: MLI-153\n');
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// Helper: drive the reporter through a full lifecycle and return the run.
async function runLifecycle(
  reporter: TestRailReporter,
  tests: FakeTest[],
  results: Array<[FakeTest, FakeResult]>,
): Promise<void> {
  reporter.onBegin!({} as never, makeSuite(tests) as never);
  for (const [t, r] of results) {
    reporter.onTestEnd!(t as never, r as never);
  }
  await reporter.onEnd!({ status: 'passed' } as never);
}

function findCall(method: string, pathFragment: string): unknown[] | undefined {
  return fetchMock.mock.calls.find(([url, init]) => {
    return (
      typeof url === 'string' &&
      url.includes(pathFragment) &&
      ((init as RequestInit | undefined)?.method ?? 'GET') === method
    );
  });
}

function parseBody(call: unknown[] | undefined): Record<string, unknown> {
  if (!call) return {};
  const init = call[1] as RequestInit;
  if (!init?.body) return {};
  return JSON.parse(init.body as string);
}

// ---------------------------------------------------------------------------

describe('TestRailReporter — happy path', () => {
  it('creates run with case_ids, posts results, closes run, writes URL', async () => {
    const test = makeTest();

    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse({
          cases: [{ id: 101, title: test.title }],
          _links: { next: null },
        });
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 555, url: 'https://example.testrail.io/index.php?/runs/view/555' });
      }
      if (method === 'POST' && url.includes('add_result_for_case/')) {
        return jsonResponse({ id: 1 });
      }
      if (method === 'POST' && url.includes('close_run/')) {
        return jsonResponse({ id: 555, is_completed: true });
      }
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    await runLifecycle(reporter, [test], [[test, makeResult()]]);

    const runCall = findCall('POST', 'add_run/42');
    expect(runCall).toBeDefined();
    const runBody = parseBody(runCall);
    expect(runBody.case_ids).toEqual([101]);
    expect(runBody.include_all).toBe(false);
    expect(runBody.suite_id).toBe(7);
    expect(runBody.name).toBe('MMFP CI 12345 (slice-01/testrail-reporter)');
    expect((runBody.description as string).includes('deadbeef')).toBe(true);

    const resultCall = findCall('POST', 'add_result_for_case/555/101');
    expect(resultCall).toBeDefined();
    expect(parseBody(resultCall).status_id).toBe(1);

    expect(findCall('POST', 'close_run/555')).toBeDefined();

    expect(writeFileMock).toHaveBeenCalledWith(
      expect.stringContaining('testrail-run-url.txt'),
      'https://example.testrail.io/index.php?/runs/view/555',
    );
  });

  it('reuses existing case_id when title matches', async () => {
    const test = makeTest();

    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse([{ id: 999, title: test.title }]);
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 1, url: 'http://run' });
      }
      if (method === 'POST') return jsonResponse({});
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    await runLifecycle(reporter, [test], [[test, makeResult()]]);

    const addCaseCalls = fetchMock.mock.calls.filter(([url, init]) =>
      typeof url === 'string' &&
      url.includes('add_case/') &&
      ((init as RequestInit | undefined)?.method === 'POST'),
    );
    expect(addCaseCalls).toHaveLength(0);
    expect(parseBody(findCall('POST', 'add_run/42')).case_ids).toEqual([999]);
  });

  it('auto-creates a case when title not found, with refs from @jira comment', async () => {
    const test = makeTest();

    let createdCaseId = 0;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse({ cases: [], _links: { next: null } });
      }
      if (method === 'GET' && url.includes('get_sections/')) {
        return jsonResponse({
          sections: [{ id: 200, name: 'Auto-imported from Playwright' }],
          _links: { next: null },
        });
      }
      if (method === 'GET' && url.includes('get_case_types')) {
        return jsonResponse([
          { id: 9, name: 'Acceptance' },
          { id: 1, name: 'Other' },
        ]);
      }
      if (method === 'POST' && url.includes('add_case/200')) {
        createdCaseId = 321;
        return jsonResponse({ id: createdCaseId, title: test.title });
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 1, url: 'http://run' });
      }
      if (method === 'POST') return jsonResponse({});
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    await runLifecycle(reporter, [test], [[test, makeResult()]]);

    const addCaseCall = findCall('POST', 'add_case/200');
    expect(addCaseCall).toBeDefined();
    const body = parseBody(addCaseCall);
    expect(body.title).toBe(test.title);
    expect(body.type_id).toBe(9);
    expect(body.refs).toBe('MLI-153');

    expect(parseBody(findCall('POST', 'add_run/42')).case_ids).toEqual([321]);
  });

  it('creates the auto-imported section if it does not exist', async () => {
    const test = makeTest();

    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse({ cases: [], _links: { next: null } });
      }
      if (method === 'GET' && url.includes('get_sections/')) {
        return jsonResponse({ sections: [], _links: { next: null } });
      }
      if (method === 'POST' && url.includes('add_section/42')) {
        return jsonResponse({ id: 77, name: 'Auto-imported from Playwright' });
      }
      if (method === 'GET' && url.includes('get_case_types')) {
        return jsonResponse([]);
      }
      if (method === 'POST' && url.includes('add_case/77')) {
        return jsonResponse({ id: 88, title: test.title });
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 1, url: 'http://run' });
      }
      if (method === 'POST') return jsonResponse({});
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    await runLifecycle(reporter, [test], [[test, makeResult()]]);

    const sectionCall = findCall('POST', 'add_section/42');
    expect(sectionCall).toBeDefined();
    expect(parseBody(sectionCall).name).toBe('Auto-imported from Playwright');
    expect(findCall('POST', 'add_case/77')).toBeDefined();
  });
});

describe('TestRailReporter — result mapping', () => {
  it('maps failed status to STATUS_FAILED on final attempt', async () => {
    const test = makeTest({ retries: 0 });

    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse([{ id: 1, title: test.title }]);
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 10, url: 'http://run' });
      }
      if (method === 'POST') return jsonResponse({});
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    const result = makeResult({
      status: 'failed',
      retry: 0,
      errors: [{ message: 'boom', stack: 'at line 1' }],
    });
    await runLifecycle(reporter, [test], [[test, result]]);

    const body = parseBody(findCall('POST', 'add_result_for_case/10/1'));
    expect(body.status_id).toBe(5);
    expect((body.comment as string).includes('boom')).toBe(true);
  });

  it('maps failed status to STATUS_RETEST when more retries remain', async () => {
    const test = makeTest({ retries: 2 });

    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse([{ id: 1, title: test.title }]);
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 10, url: 'http://run' });
      }
      if (method === 'POST') return jsonResponse({});
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    const result = makeResult({ status: 'failed', retry: 0 });
    await runLifecycle(reporter, [test], [[test, result]]);

    const body = parseBody(findCall('POST', 'add_result_for_case/10/1'));
    expect(body.status_id).toBe(4);
  });

  it('does not post for skipped tests', async () => {
    const test = makeTest();

    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse([{ id: 1, title: test.title }]);
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 10, url: 'http://run' });
      }
      if (method === 'POST') return jsonResponse({});
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    await runLifecycle(reporter, [test], [[test, makeResult({ status: 'skipped' })]]);

    expect(findCall('POST', 'add_result_for_case/')).toBeUndefined();
  });
});

describe('TestRailReporter — slice derivation', () => {
  it('derives suite id from a slice-NpM filename (e.g. slice-3p5) without colliding with slice-N', async () => {
    vi.stubEnv('TESTRAIL_SUITE_SLICE_03', '67');
    vi.stubEnv('TESTRAIL_SUITE_SLICE_03P5', '89');

    const test = makeTest({
      location: {
        file: '/repo/tests/e2e/slice-3p5-editor-and-scoreboard.spec.ts',
        line: 1,
        column: 1,
      },
    });

    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse([{ id: 1, title: test.title }]);
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 1, url: 'http://run' });
      }
      if (method === 'POST') return jsonResponse({});
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    await runLifecycle(reporter, [test], [[test, makeResult()]]);

    expect(parseBody(findCall('POST', 'add_run/42')).suite_id).toBe(89);
  });

  it('derives suite id from a plain slice-NN filename (slice-03)', async () => {
    vi.stubEnv('TESTRAIL_SUITE_SLICE_03', '67');

    const test = makeTest({
      location: {
        file: '/repo/tests/e2e/slice-03-trends.spec.ts',
        line: 1,
        column: 1,
      },
    });

    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse([{ id: 1, title: test.title }]);
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return jsonResponse({ id: 1, url: 'http://run' });
      }
      if (method === 'POST') return jsonResponse({});
      throw new Error(`unexpected fetch: ${method} ${url}`);
    });

    const reporter = new TestRailReporter();
    await runLifecycle(reporter, [test], [[test, makeResult()]]);

    expect(parseBody(findCall('POST', 'add_run/42')).suite_id).toBe(67);
  });
});

describe('TestRailReporter — fail-safe', () => {
  it('is a no-op when env vars are unset (does not throw, does not call fetch)', async () => {
    vi.unstubAllEnvs(); // wipe everything beforeEach set up
    vi.stubEnv('GITHUB_RUN_ID', ''); // also clear github vars

    const reporter = new TestRailReporter();
    const test = makeTest();
    await expect(
      runLifecycle(reporter, [test], [[test, makeResult()]]),
    ).resolves.toBeUndefined();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(writeFileMock).not.toHaveBeenCalled();
    // Confirms the spec's exact warning string.
    expect(warnSpy).toHaveBeenCalledWith('[testrail-reporter] env vars missing, no-op');
  });

  it('is a no-op when slice-suite env var is missing', async () => {
    vi.stubEnv('TESTRAIL_SUITE_SLICE_01', '');

    const reporter = new TestRailReporter();
    const test = makeTest();
    await expect(
      runLifecycle(reporter, [test], [[test, makeResult()]]),
    ).resolves.toBeUndefined();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not propagate errors when fetch throws on every call', async () => {
    fetchMock.mockRejectedValue(new Error('network is down'));

    const reporter = new TestRailReporter();
    const test = makeTest();
    await expect(
      runLifecycle(reporter, [test], [[test, makeResult()]]),
    ).resolves.toBeUndefined();

    // The reporter must have logged the failure but still allowed the run to
    // complete cleanly. The Playwright run, in production, would have already
    // succeeded by this point regardless of the reporter.
    expect(errorSpy).toHaveBeenCalled();
  });

  it('does not propagate errors when TestRail returns 500', async () => {
    fetchMock.mockResolvedValue(new Response('boom', { status: 500 }));

    const reporter = new TestRailReporter();
    const test = makeTest();
    await expect(
      runLifecycle(reporter, [test], [[test, makeResult()]]),
    ).resolves.toBeUndefined();

    expect(errorSpy).toHaveBeenCalled();
  });

  it('continues as no-op for results when run creation fails', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url.includes('get_cases/')) {
        return jsonResponse([{ id: 1, title: 'walking skeleton: scorecard page displays hardcoded score' }]);
      }
      if (method === 'POST' && url.includes('add_run/')) {
        return new Response('server error', { status: 500 });
      }
      return jsonResponse({});
    });

    const reporter = new TestRailReporter();
    const test = makeTest();
    await runLifecycle(reporter, [test], [[test, makeResult()]]);

    // No result and no close_run should have been issued.
    expect(findCall('POST', 'add_result_for_case/')).toBeUndefined();
    expect(findCall('POST', 'close_run/')).toBeUndefined();
  });
});
