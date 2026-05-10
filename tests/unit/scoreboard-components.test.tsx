// Unit tests for TierCard and Scorecard components (MLI-175).
//
// These components are synchronous server components — no React hooks, no
// client-side state. RTL renders them directly without async wrappers.
//
// What we exercise:
//   - Testids required by the slice-02 Playwright acceptance test
//   - Human-readable text the acceptance test or rubric contract expects
//   - Edge cases: empty candidates, (unknown) deployment badge, Tier 3 note

import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
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
});
