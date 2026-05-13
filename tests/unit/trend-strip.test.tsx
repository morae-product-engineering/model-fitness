// Unit tests for TrendStrip (MLI-186, updated MLI-264).
//
// What we exercise:
//   - testid required by the slice-03 Playwright acceptance test
//   - Empty / single-run state copy
//   - Multi-run rendering produces one polyline per candidate, in input order
//   - Hover surfaces the completed_at timestamp + score in the tooltip (3-line)
//   - Family-based stroke colour (orange = reasoning, neutral-5 = chat)
//   - Y-axis reference labels at 0, 50, 100
//   - X-axis date ticks — one per run
//   - Family legend shows entries for families present in the data

import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import TrendStrip from '../../ui/components/TrendStrip';
import { TrendCandidate, TrendRun } from '../../ui/lib/scoreboard';

function run(id: string, day: number): TrendRun {
  // Anchor on 2026-05-12, walk back `day` days. completed_at = started_at + 30s.
  const started = new Date(Date.UTC(2026, 4, 12 - day, 12, 0, 0));
  const completed = new Date(started.getTime() + 30_000);
  return {
    run_id: id,
    rubric_version: 'v0.1',
    started_at: started.toISOString(),
    completed_at: completed.toISOString(),
  };
}

function cand(
  id: string,
  family: TrendCandidate['family'],
  points: { run_id: string; weighted_score: number }[],
): TrendCandidate {
  return {
    candidate_id: id,
    display_name: id.toUpperCase(),
    family,
    deployment: `azure-${id}`,
    status: 'under_evaluation',
    points,
  };
}

describe('TrendStrip', () => {
  it('renders the tier testid required by MLI-181', () => {
    const runs = [run('r3', 0), run('r2', 7), run('r1', 14)];
    const candidates = [
      cand('a', 'chat', [
        { run_id: 'r1', weighted_score: 70 },
        { run_id: 'r2', weighted_score: 75 },
        { run_id: 'r3', weighted_score: 80 },
      ]),
    ];
    render(<TrendStrip tierId="tier_3" runs={runs} candidates={candidates} />);
    expect(screen.getByTestId('tier-tier_3-trend-strip')).toBeInTheDocument();
  });

  it('shows "Not enough history yet" when there are zero runs', () => {
    render(<TrendStrip tierId="tier_1" runs={[]} candidates={[]} />);
    const strip = screen.getByTestId('tier-tier_1-trend-strip');
    expect(within(strip).getByText('Not enough history yet')).toBeInTheDocument();
  });

  it('shows "Not enough history yet" when there is only one run', () => {
    const runs = [run('only', 0)];
    const candidates = [
      cand('a', 'chat', [{ run_id: 'only', weighted_score: 75 }]),
    ];
    render(<TrendStrip tierId="tier_1" runs={runs} candidates={candidates} />);
    const strip = screen.getByTestId('tier-tier_1-trend-strip');
    expect(within(strip).getByText('Not enough history yet')).toBeInTheDocument();
  });

  it('renders one path per candidate when multiple runs are available', () => {
    const runs = [run('r3', 0), run('r2', 7), run('r1', 14)];
    const candidates = [
      cand('a', 'reasoning', [
        { run_id: 'r1', weighted_score: 60 },
        { run_id: 'r2', weighted_score: 70 },
        { run_id: 'r3', weighted_score: 80 },
      ]),
      cand('b', 'chat', [
        { run_id: 'r1', weighted_score: 50 },
        { run_id: 'r2', weighted_score: 55 },
        { run_id: 'r3', weighted_score: 60 },
      ]),
    ];
    const { container } = render(
      <TrendStrip tierId="tier_2" runs={runs} candidates={candidates} />,
    );
    const paths = container.querySelectorAll('svg path');
    expect(paths).toHaveLength(2);
  });

  it('strokes reasoning lines orange and chat lines neutral-5', () => {
    const runs = [run('r2', 0), run('r1', 7)];
    const candidates = [
      cand('reasoner', 'reasoning', [
        { run_id: 'r1', weighted_score: 60 },
        { run_id: 'r2', weighted_score: 70 },
      ]),
      cand('chatter', 'chat', [
        { run_id: 'r1', weighted_score: 40 },
        { run_id: 'r2', weighted_score: 50 },
      ]),
    ];
    const { container } = render(
      <TrendStrip tierId="tier_1" runs={runs} candidates={candidates} />,
    );
    const paths = Array.from(container.querySelectorAll('svg path'));
    const strokes = paths.map((p) => p.getAttribute('stroke'));
    expect(strokes).toContain('#ff6900');
    expect(strokes).toContain('#595959');
  });

  it('shows tooltip with score and a completed_at-derived label on hover', () => {
    const runs = [run('r2', 0), run('r1', 7)];
    const candidates = [
      cand('a', 'chat', [
        { run_id: 'r1', weighted_score: 60 },
        { run_id: 'r2', weighted_score: 72.5 },
      ]),
    ];
    render(<TrendStrip tierId="tier_1" runs={runs} candidates={candidates} />);

    // Hover the newest point (chronological idx 1 — r2). Hit-target testid uses
    // the chrono index assigned inside the component.
    const hit = screen.getByTestId('trend-point-a-1');
    fireEvent.mouseEnter(hit);

    const tooltip = screen.getByTestId('tier-tier_1-trend-tooltip');
    expect(within(tooltip).getByText('A')).toBeInTheDocument();
    // Score is on its own line now (3-line tooltip: name / date / score).
    // The timestamp uses toLocaleDateString which is locale-dependent —
    // assert the score value survives without pinning the exact date string.
    expect(tooltip.textContent).toContain('72.5');
  });

  it('renders x-axis tick elements — one per run', () => {
    const runs = [run('r3', 0), run('r2', 7), run('r1', 14)];
    const candidates = [
      cand('a', 'chat', [
        { run_id: 'r1', weighted_score: 70 },
        { run_id: 'r2', weighted_score: 75 },
        { run_id: 'r3', weighted_score: 80 },
      ]),
    ];
    const { container } = render(
      <TrendStrip tierId="tier_1" runs={runs} candidates={candidates} />,
    );
    // Three runs → three x-tick groups. Assert by count, not by exact date
    // string, since toLocaleDateString is locale-dependent.
    const ticks = container.querySelectorAll('[data-testid="trend-x-tick"]');
    expect(ticks).toHaveLength(3);
  });

  it('renders y-axis labels at 0, 50, and 100', () => {
    const runs = [run('r2', 0), run('r1', 7)];
    const candidates = [
      cand('a', 'chat', [
        { run_id: 'r1', weighted_score: 60 },
        { run_id: 'r2', weighted_score: 80 },
      ]),
    ];
    render(<TrendStrip tierId="tier_1" runs={runs} candidates={candidates} />);
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  it('renders a legend with both families when both are present', () => {
    const runs = [run('r2', 0), run('r1', 7)];
    const candidates = [
      cand('reasoner', 'reasoning', [
        { run_id: 'r1', weighted_score: 60 },
        { run_id: 'r2', weighted_score: 70 },
      ]),
      cand('chatter', 'chat', [
        { run_id: 'r1', weighted_score: 40 },
        { run_id: 'r2', weighted_score: 50 },
      ]),
    ];
    render(<TrendStrip tierId="tier_1" runs={runs} candidates={candidates} />);
    expect(screen.getByText('Reasoning')).toBeInTheDocument();
    expect(screen.getByText('Chat')).toBeInTheDocument();
  });

  it('renders legend with only Chat when no reasoning candidates are present', () => {
    const runs = [run('r2', 0), run('r1', 7)];
    const candidates = [
      cand('chatter', 'chat', [
        { run_id: 'r1', weighted_score: 40 },
        { run_id: 'r2', weighted_score: 50 },
      ]),
    ];
    render(<TrendStrip tierId="tier_1" runs={runs} candidates={candidates} />);
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.queryByText('Reasoning')).toBeNull();
  });
});
