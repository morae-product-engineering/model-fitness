// Unit tests for TierCard and Scorecard components (MLI-175, extended in MLI-185).
//
// These components are synchronous server components — no React hooks, no
// client-side state. RTL renders them directly without async wrappers.
//
// What we exercise:
//   - Testids required by the slice-02/slice-03 Playwright acceptance tests
//   - Human-readable text the acceptance test or rubric contract expects
//   - Edge cases: empty candidates, (unknown) deployment badge, Tier 3 note
//   - MLI-185: score-descending render order incl. all-equal stability,
//     and FamilyDot family-icon presence per candidate.

import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import TierCard from '../../ui/components/TierCard';
import Scorecard from '../../ui/components/Scorecard';
import { TIERS, Candidate, TierId } from '../../ui/lib/scoreboard';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeCandidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    candidate_id: 'gpt-4o',
    display_name: 'GPT-4o',
    family: 'chat',
    deployment: 'azure-gpt-4o',
    status: 'under_evaluation',
    weighted_score: 82.5,
    per_dimension: { accuracy: 85.0, latency: 78.0 },
    ...overrides,
  };
}

const TIER_1: TierId = 'tier_1';
const TIER_3: TierId = 'tier_3';

// ---------------------------------------------------------------------------
// TierCard
// ---------------------------------------------------------------------------

describe('TierCard', () => {
  it('renders with the correct tier testid', () => {
    render(
      <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={[makeCandidate()]} />
    );
    expect(screen.getByTestId('tier-card-tier_1')).toBeInTheDocument();
  });

  it('shows the tier title from TIERS metadata', () => {
    render(
      <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={[makeCandidate()]} />
    );
    expect(screen.getByText(TIERS[TIER_1].title)).toBeInTheDocument();
  });

  it('shows candidate count in the header', () => {
    const candidates = [makeCandidate(), makeCandidate({ candidate_id: 'claude-3' })];
    render(
      <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={candidates} />
    );
    expect(screen.getByText('2 candidates')).toBeInTheDocument();
  });

  it('shows singular candidate count when there is exactly one', () => {
    render(
      <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={[makeCandidate()]} />
    );
    expect(screen.getByText('1 candidate')).toBeInTheDocument();
  });

  it('shows empty-state copy when candidates array is empty', () => {
    render(
      <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={[]} />
    );
    expect(screen.getByTestId('tier-card-tier_1')).toBeInTheDocument();
    expect(screen.getByText('No scored candidates')).toBeInTheDocument();
  });

  it('renders the Tier 3 synthesis-emphasis note', () => {
    render(
      <TierCard tierId={TIER_3} meta={TIERS[TIER_3]} candidates={[makeCandidate()]} />
    );
    expect(screen.getByText(TIERS[TIER_3].note!)).toBeInTheDocument();
  });

  it('does not render a note for Tier 1 (no note in metadata)', () => {
    render(
      <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={[makeCandidate()]} />
    );
    // TIERS[tier_1].note is undefined; we verify no synthesis note leaks in.
    expect(screen.queryByText(/v0\.1 — deterministic/)).not.toBeInTheDocument();
  });

  // MLI-185 — ranked candidates per tier
  describe('ranked render order', () => {
    it('renders the single candidate when slate has one entry', () => {
      render(
        <TierCard
          tierId={TIER_1}
          meta={TIERS[TIER_1]}
          candidates={[makeCandidate({ candidate_id: 'solo', display_name: 'Solo' })]}
        />
      );
      const rows = screen.getAllByTestId('tier-tier_1-candidate');
      expect(rows).toHaveLength(1);
      expect(within(rows[0]!).getByText('Solo')).toBeInTheDocument();
    });

    it('renders multiple candidates in score-descending order regardless of input order', () => {
      // Deliberately scrambled input order — the component must rank.
      const candidates = [
        makeCandidate({ candidate_id: 'mid', display_name: 'Mid', weighted_score: 70.0 }),
        makeCandidate({ candidate_id: 'top', display_name: 'Top', weighted_score: 90.0 }),
        makeCandidate({ candidate_id: 'low', display_name: 'Low', weighted_score: 50.0 }),
      ];
      render(
        <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={candidates} />
      );
      const rows = screen.getAllByTestId('tier-tier_1-candidate');
      expect(rows).toHaveLength(3);
      expect(within(rows[0]!).getByTestId('candidate-score')).toHaveTextContent('90.0');
      expect(within(rows[1]!).getByTestId('candidate-score')).toHaveTextContent('70.0');
      expect(within(rows[2]!).getByTestId('candidate-score')).toHaveTextContent('50.0');
    });

    it('preserves input order for candidates with equal scores (stable sort)', () => {
      const candidates = [
        makeCandidate({ candidate_id: 'a', display_name: 'A', weighted_score: 80.0 }),
        makeCandidate({ candidate_id: 'b', display_name: 'B', weighted_score: 80.0 }),
        makeCandidate({ candidate_id: 'c', display_name: 'C', weighted_score: 80.0 }),
      ];
      render(
        <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={candidates} />
      );
      const rows = screen.getAllByTestId('tier-tier_1-candidate');
      expect(within(rows[0]!).getByText('A')).toBeInTheDocument();
      expect(within(rows[1]!).getByText('B')).toBeInTheDocument();
      expect(within(rows[2]!).getByText('C')).toBeInTheDocument();
    });

    it('renders no candidate rows when the tier is empty', () => {
      render(
        <TierCard tierId={TIER_1} meta={TIERS[TIER_1]} candidates={[]} />
      );
      expect(screen.queryAllByTestId('tier-tier_1-candidate')).toHaveLength(0);
    });
  });
});

// ---------------------------------------------------------------------------
// Scorecard
// ---------------------------------------------------------------------------

describe('Scorecard', () => {
  it('renders one row per candidate with the correct testid', () => {
    const candidates = [
      makeCandidate({ candidate_id: 'a', display_name: 'Model A' }),
      makeCandidate({ candidate_id: 'b', display_name: 'Model B' }),
    ];
    render(<Scorecard tierId={TIER_1} candidates={candidates} />);
    const rows = screen.getAllByTestId('tier-tier_1-candidate');
    expect(rows).toHaveLength(2);
  });

  it('candidate-score testid contains the score formatted to 1 dp', () => {
    const c = makeCandidate({ weighted_score: 82.543 });
    render(<Scorecard tierId={TIER_1} candidates={[c]} />);
    const scoreEl = screen.getByTestId('candidate-score');
    expect(scoreEl).toHaveTextContent('82.5');
  });

  it('derives dimension column headers from the first candidate', () => {
    const c = makeCandidate({
      per_dimension: { accuracy: 90.0, latency: 70.0, cost: 55.0 },
    });
    render(<Scorecard tierId={TIER_1} candidates={[c]} />);
    expect(screen.getByText('accuracy')).toBeInTheDocument();
    expect(screen.getByText('latency')).toBeInTheDocument();
    expect(screen.getByText('cost')).toBeInTheDocument();
  });

  it('renders (unknown) badge when deployment is "(unknown)"', () => {
    const c = makeCandidate({ deployment: '(unknown)' });
    render(<Scorecard tierId={TIER_1} candidates={[c]} />);
    const row = screen.getByTestId('tier-tier_1-candidate');
    // The deployment value "(unknown)" appears in both the badge span and the
    // deployment cell, so we assert at least one match inside the row.
    const matches = within(row).getAllByText('(unknown)');
    expect(matches.length).toBeGreaterThanOrEqual(1);
    // At least one match must be the badge span (has the bg-neutral-12 badge class).
    const badge = matches.find((el) => el.tagName.toLowerCase() === 'span');
    expect(badge).toBeDefined();
  });

  it('renders nothing when candidates array is empty', () => {
    const { container } = render(<Scorecard tierId={TIER_1} candidates={[]} />);
    expect(container.firstChild).toBeNull();
  });

  // MLI-185 — family icon per candidate
  describe('family icon', () => {
    it('renders the chat family icon for a chat candidate', () => {
      render(
        <Scorecard
          tierId={TIER_1}
          candidates={[makeCandidate({ family: 'chat' })]}
        />
      );
      const row = screen.getByTestId('tier-tier_1-candidate');
      expect(within(row).getByTestId('family-icon-chat')).toBeInTheDocument();
    });

    it('renders the reasoning family icon for a reasoning candidate', () => {
      render(
        <Scorecard
          tierId={TIER_1}
          candidates={[makeCandidate({ family: 'reasoning' })]}
        />
      );
      const row = screen.getByTestId('tier-tier_1-candidate');
      expect(within(row).getByTestId('family-icon-reasoning')).toBeInTheDocument();
    });

    it('renders one family icon per candidate when the tier has many', () => {
      const candidates = [
        makeCandidate({ candidate_id: 'a', family: 'chat' }),
        makeCandidate({ candidate_id: 'b', family: 'reasoning' }),
        makeCandidate({ candidate_id: 'c', family: 'chat' }),
      ];
      render(<Scorecard tierId={TIER_1} candidates={candidates} />);
      expect(screen.getAllByTestId('family-icon-chat')).toHaveLength(2);
      expect(screen.getAllByTestId('family-icon-reasoning')).toHaveLength(1);
    });
  });

  // MLI-187 — row click opens the candidate-detail drill-down
  describe('drill-down', () => {
    afterEach(() => {
      vi.unstubAllGlobals();
      vi.restoreAllMocks();
    });

    it('rows are not clickable when product/apiBaseUrl are omitted', () => {
      render(<Scorecard tierId={TIER_1} candidates={[makeCandidate()]} />);
      const row = screen.getByTestId('tier-tier_1-candidate');
      // No role=button → static row, no click affordance.
      expect(row.getAttribute('role')).toBeNull();
      fireEvent.click(row);
      expect(screen.queryByTestId('candidate-detail-overlay')).not.toBeInTheDocument();
    });

    it('opens the candidate-detail modal when a row is clicked', async () => {
      // Stub fetch so the opened modal can resolve without a real network call.
      vi.stubGlobal(
        'fetch',
        vi.fn(
          async () =>
            new Response(
              JSON.stringify({
                product: 'mli',
                candidate_id: 'gpt-4o',
                display_name: 'GPT-4o',
                family: 'chat',
                deployment: 'azure-gpt-4o',
                status: 'under_evaluation',
                tiers: ['tier_1'],
                latest_run: null,
                history: [],
              }),
              { status: 200 },
            ),
        ),
      );
      render(
        <Scorecard
          tierId={TIER_1}
          candidates={[makeCandidate()]}
          product="mli"
          apiBaseUrl="http://api.test"
        />,
      );
      const row = screen.getByTestId('tier-tier_1-candidate');
      expect(row.getAttribute('role')).toBe('button');
      fireEvent.click(row);
      expect(screen.getByTestId('candidate-detail-overlay')).toBeInTheDocument();
    });
  });
});
