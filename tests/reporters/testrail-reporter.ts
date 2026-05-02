import * as fs from 'fs';
import * as path from 'path';
import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestResult,
} from '@playwright/test/reporter';

// Fail-safe Playwright -> TestRail reporter.
//
// Behaviour is specced in MLI-218. Two non-obvious invariants:
//
// 1. Every TestRail interaction is wrapped so the reporter can NEVER fail a
//    Playwright run. On any unexpected error we flip into "degraded" mode and
//    subsequent calls become no-ops. This is the headline acceptance criterion.
//
// 2. Cases are matched-or-created by *test title*, not by `@C{n}` tags. The
//    test code is the source of truth for the TestRail catalogue. See the
//    "Why title-matching" section of MLI-218 for the rationale.

const LOG_PREFIX = '[testrail-reporter]';
const AUTO_SECTION_NAME = 'Auto-imported from Playwright';
const ACCEPTANCE_TYPE_NAME = 'Acceptance';

// TestRail status IDs are stable defaults across installs.
const STATUS_PASSED = 1;
const STATUS_RETEST = 4;
const STATUS_FAILED = 5;

interface TestRailEnv {
  url: string;
  user: string;
  apiKey: string;
  projectId: number;
  suiteId: number;
}

interface TestRailCase {
  id: number;
  title: string;
}

interface TestRailSection {
  id: number;
  name: string;
}

interface TestRailType {
  id: number;
  name: string;
}

interface TestRailRun {
  id: number;
  url: string;
}

interface PaginatedResponse<T> {
  cases?: T[];
  sections?: T[];
  _links?: { next?: string | null };
}

export default class TestRailReporter implements Reporter {
  private env: TestRailEnv | null = null;
  private degraded = false;
  private setupPromise: Promise<void> = Promise.resolve();
  private resultChain: Promise<void> = Promise.resolve();
  private titleToCaseId: Map<string, number> = new Map();
  private runId: number | null = null;

  // ---- lifecycle ---------------------------------------------------------

  onBegin(_config: FullConfig, suite: Suite): void {
    // Setup is async (multiple TestRail calls) but Playwright doesn't await
    // onBegin. We stash the promise and chain later hooks off it so test
    // results don't try to post before the run exists.
    this.setupPromise = this.setup(suite).catch((err) => {
      this.logError('setup', err);
      this.degraded = true;
    });
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    // Chain results so we (a) wait for setup and (b) preserve order.
    this.resultChain = this.resultChain.then(async () => {
      try {
        await this.setupPromise;
        if (this.degraded || this.runId === null) return;
        await this.postResult(test, result);
      } catch (err) {
        this.logError('onTestEnd', err);
      }
    });
  }

  async onEnd(_result: FullResult): Promise<void> {
    try {
      await this.setupPromise;
      await this.resultChain;
      if (this.degraded || this.runId === null) return;
      await this.closeRun();
    } catch (err) {
      this.logError('onEnd', err);
    }
  }

  // ---- setup -------------------------------------------------------------

  private async setup(suite: Suite): Promise<void> {
    const env = this.readEnv(suite);
    if (env === null) {
      this.degraded = true;
      return;
    }
    this.env = env;

    const tests = suite.allTests();
    if (tests.length === 0) {
      console.warn(`${LOG_PREFIX} no tests in suite, no-op`);
      this.degraded = true;
      return;
    }

    const existingCases = await this.fetchExistingCases();
    let sectionId: number | null = null;
    let typeId: number | null = null;

    for (const test of tests) {
      const title = test.title;
      const existing = existingCases.get(title);
      if (existing !== undefined) {
        this.titleToCaseId.set(title, existing);
        continue;
      }

      // Lazily resolve section + type only if we actually need to create a case.
      if (sectionId === null) sectionId = await this.ensureSection();
      if (sectionId === null) {
        // Couldn't resolve section -> can't create cases. Skip this test;
        // existing-case tests above are already mapped.
        continue;
      }
      if (typeId === null) typeId = await this.findAcceptanceTypeId();

      const refs = this.parseJiraRef(test.location.file);
      const newId = await this.createCase(sectionId, title, typeId, refs);
      if (newId !== null) {
        this.titleToCaseId.set(title, newId);
      }
    }

    const caseIds = Array.from(this.titleToCaseId.values());
    if (caseIds.length === 0) {
      console.warn(`${LOG_PREFIX} no cases resolved, skipping run creation`);
      this.degraded = true;
      return;
    }

    const run = await this.createRun(caseIds);
    if (run === null) {
      this.degraded = true;
      return;
    }
    this.runId = run.id;
    this.writeRunUrl(run.url);
  }

  private readEnv(suite: Suite): TestRailEnv | null {
    const url = process.env.TESTRAIL_URL;
    const user = process.env.TESTRAIL_USER;
    const apiKey = process.env.TESTRAIL_API_KEY;
    const projectIdStr = process.env.TESTRAIL_PROJECT_ID;

    if (!url || !user || !apiKey || !projectIdStr) {
      console.warn(`${LOG_PREFIX} env vars missing, no-op`);
      return null;
    }

    const projectId = Number.parseInt(projectIdStr, 10);
    if (Number.isNaN(projectId)) {
      console.warn(`${LOG_PREFIX} TESTRAIL_PROJECT_ID is not a number, no-op`);
      return null;
    }

    const sliceNumber = this.deriveSliceNumber(suite);
    if (sliceNumber === null) {
      console.warn(`${LOG_PREFIX} could not derive slice number from test paths, no-op`);
      return null;
    }

    const suiteEnvKey = `TESTRAIL_SUITE_SLICE_${String(sliceNumber).padStart(2, '0')}`;
    const suiteIdStr = process.env[suiteEnvKey];
    if (!suiteIdStr) {
      console.warn(`${LOG_PREFIX} ${suiteEnvKey} not set, no-op`);
      return null;
    }
    const suiteId = Number.parseInt(suiteIdStr, 10);
    if (Number.isNaN(suiteId)) {
      console.warn(`${LOG_PREFIX} ${suiteEnvKey} is not a number, no-op`);
      return null;
    }

    // Strip trailing slash for clean URL composition.
    return { url: url.replace(/\/$/, ''), user, apiKey, projectId, suiteId };
  }

  private deriveSliceNumber(suite: Suite): number | null {
    const re = /slice-(\d+)/i;
    for (const test of suite.allTests()) {
      const m = test.location.file.match(re);
      if (m) return Number.parseInt(m[1], 10);
    }
    return null;
  }

  private parseJiraRef(filePath: string): string | undefined {
    try {
      const content = fs.readFileSync(filePath, 'utf-8');
      const m = content.match(/\/\/\s*@jira:\s*([A-Z]+-\d+)/);
      return m ? m[1] : undefined;
    } catch (err) {
      this.logError('parseJiraRef', err);
      return undefined;
    }
  }

  // ---- TestRail API wrappers --------------------------------------------

  private async fetchExistingCases(): Promise<Map<string, number>> {
    const map = new Map<string, number>();
    if (!this.env) return map;

    let nextPath: string | null =
      `/api/v2/get_cases/${this.env.projectId}&suite_id=${this.env.suiteId}`;
    let safetyHops = 0;
    while (nextPath !== null && safetyHops < 50) {
      safetyHops += 1;
      const data = await this.api<TestRailCase[] | PaginatedResponse<TestRailCase>>(
        'GET',
        nextPath,
      );
      if (data === null) break;
      const list: TestRailCase[] = Array.isArray(data) ? data : data.cases ?? [];
      for (const c of list) {
        if (c && typeof c.id === 'number' && typeof c.title === 'string') {
          map.set(c.title, c.id);
        }
      }
      nextPath = !Array.isArray(data) && data._links?.next ? data._links.next : null;
    }
    return map;
  }

  private async ensureSection(): Promise<number | null> {
    if (!this.env) return null;

    const data = await this.api<TestRailSection[] | PaginatedResponse<TestRailSection>>(
      'GET',
      `/api/v2/get_sections/${this.env.projectId}&suite_id=${this.env.suiteId}`,
    );
    if (data !== null) {
      const list: TestRailSection[] = Array.isArray(data) ? data : data.sections ?? [];
      const found = list.find((s) => s.name === AUTO_SECTION_NAME);
      if (found) return found.id;
    }

    const created = await this.api<TestRailSection>(
      'POST',
      `/api/v2/add_section/${this.env.projectId}`,
      { suite_id: this.env.suiteId, name: AUTO_SECTION_NAME },
    );
    return created?.id ?? null;
  }

  private async findAcceptanceTypeId(): Promise<number | null> {
    const data = await this.api<TestRailType[]>('GET', '/api/v2/get_case_types');
    if (!data || !Array.isArray(data)) return null;
    const found = data.find((t) => t.name === ACCEPTANCE_TYPE_NAME);
    return found?.id ?? null;
  }

  private async createCase(
    sectionId: number,
    title: string,
    typeId: number | null,
    refs: string | undefined,
  ): Promise<number | null> {
    const body: Record<string, unknown> = { title };
    if (typeId !== null) body.type_id = typeId;
    if (refs) body.refs = refs;
    const created = await this.api<TestRailCase>('POST', `/api/v2/add_case/${sectionId}`, body);
    return created?.id ?? null;
  }

  private async createRun(caseIds: number[]): Promise<TestRailRun | null> {
    if (!this.env) return null;
    const runId = process.env.GITHUB_RUN_ID || 'local';
    const refName = process.env.GITHUB_REF_NAME || 'unknown';
    const sha = process.env.GITHUB_SHA || 'unknown';
    const server = process.env.GITHUB_SERVER_URL || 'https://github.com';
    const repo = process.env.GITHUB_REPOSITORY || '';
    const runUrl =
      process.env.GITHUB_RUN_ID && repo
        ? `${server}/${repo}/actions/runs/${process.env.GITHUB_RUN_ID}`
        : 'local run';

    const body = {
      suite_id: this.env.suiteId,
      name: `MMFP CI ${runId} (${refName})`,
      description: `GitHub Actions run: ${runUrl}\nCommit: ${sha}`,
      include_all: false,
      case_ids: caseIds,
    };
    return this.api<TestRailRun>('POST', `/api/v2/add_run/${this.env.projectId}`, body);
  }

  private async postResult(test: TestCase, result: TestResult): Promise<void> {
    if (this.runId === null) return;
    const caseId = this.titleToCaseId.get(test.title);
    if (caseId === undefined) return;

    const statusId = this.mapStatus(test, result);
    if (statusId === null) return; // skipped/interrupted -> don't post

    const body = {
      status_id: statusId,
      comment: this.buildComment(result),
      elapsed: this.formatElapsed(result.duration),
    };
    await this.api(
      'POST',
      `/api/v2/add_result_for_case/${this.runId}/${caseId}`,
      body,
    );
  }

  private async closeRun(): Promise<void> {
    if (this.runId === null) return;
    await this.api('POST', `/api/v2/close_run/${this.runId}`, {});
  }

  // ---- helpers -----------------------------------------------------------

  private mapStatus(test: TestCase, result: TestResult): number | null {
    if (result.status === 'passed') return STATUS_PASSED;
    if (result.status === 'failed' || result.status === 'timedOut') {
      // ASSUMES: result.retry is the 0-based current attempt index, and
      // test.retries is the configured max. If more retries remain, mark
      // "retest" so the failed attempt isn't recorded as final.
      if (result.retry < test.retries) return STATUS_RETEST;
      return STATUS_FAILED;
    }
    return null;
  }

  private buildComment(result: TestResult): string {
    if (result.status === 'passed') return 'Passed';
    const parts: string[] = [];
    for (const err of result.errors ?? []) {
      if (err.message) parts.push(err.message);
      if (err.stack) parts.push(err.stack);
    }
    if (parts.length === 0 && result.error?.message) {
      parts.push(result.error.message);
      if (result.error.stack) parts.push(result.error.stack);
    }
    return parts.join('\n\n').trim() || `Status: ${result.status}`;
  }

  private formatElapsed(durationMs: number): string {
    // TestRail rejects "0s"; clamp to at least 1 second.
    const seconds = Math.max(1, Math.round(durationMs / 1000));
    return `${seconds}s`;
  }

  private writeRunUrl(url: string): void {
    try {
      fs.writeFileSync(path.join(process.cwd(), 'testrail-run-url.txt'), url);
    } catch (err) {
      this.logError('writeRunUrl', err);
    }
  }

  private async api<T = unknown>(
    method: 'GET' | 'POST',
    apiPath: string,
    body?: unknown,
  ): Promise<T | null> {
    if (!this.env) return null;
    try {
      const url = `${this.env.url}/index.php?${apiPath}`;
      const auth = Buffer.from(`${this.env.user}:${this.env.apiKey}`).toString('base64');
      const headers: Record<string, string> = {
        Authorization: `Basic ${auth}`,
        'Content-Type': 'application/json',
      };
      const res = await fetch(url, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const text = await this.safeReadText(res);
        console.error(
          `${LOG_PREFIX} ${method} ${apiPath} -> ${res.status} ${res.statusText}: ${text}`,
        );
        return null;
      }
      return (await res.json()) as T;
    } catch (err) {
      this.logError(`api ${method} ${apiPath}`, err);
      return null;
    }
  }

  private async safeReadText(res: Response): Promise<string> {
    try {
      return await res.text();
    } catch {
      return '<no body>';
    }
  }

  private logError(context: string, err: unknown): void {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`${LOG_PREFIX} ${context}: ${msg}`);
  }
}
