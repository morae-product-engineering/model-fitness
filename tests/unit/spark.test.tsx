// Unit tests for the Spark primitive (MLI-264).
//
// What we exercise:
//   - Empty/single-point data renders an empty SVG (no path)
//   - Multi-point data renders exactly one path
//   - The last-point dot renders at r=2.5; all prior points at r=0

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import Spark from '../../ui/components/primitives/Spark';

describe('Spark', () => {
  it('renders an empty SVG for empty data', () => {
    const { container } = render(<Spark data={[]} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
    expect(container.querySelector('path')).toBeNull();
  });

  it('renders an empty SVG for a single non-null point', () => {
    const { container } = render(<Spark data={[42]} />);
    expect(container.querySelector('path')).toBeNull();
  });

  it('renders an empty SVG when all points are null', () => {
    const { container } = render(<Spark data={[null, null]} />);
    expect(container.querySelector('path')).toBeNull();
  });

  it('renders exactly one path for multi-point data', () => {
    const { container } = render(<Spark data={[10, 20, 30]} />);
    const paths = container.querySelectorAll('path');
    expect(paths).toHaveLength(1);
  });

  it('renders the last-point dot at r=2.5 and prior dots at r=0', () => {
    const { container } = render(<Spark data={[10, 20, 30]} />);
    const circles = Array.from(container.querySelectorAll('circle'));
    // Three points → three circles. Only the last one is visible (r=2.5).
    expect(circles).toHaveLength(3);
    const radii = circles.map((c) => parseFloat(c.getAttribute('r') ?? '0'));
    expect(radii[0]).toBe(0);
    expect(radii[1]).toBe(0);
    expect(radii[2]).toBe(2.5);
  });

  it('handles null gaps — renders a path and skips null dot', () => {
    const { container } = render(<Spark data={[10, null, 30]} />);
    expect(container.querySelector('path')).not.toBeNull();
    // Only two non-null circles rendered.
    const circles = container.querySelectorAll('circle');
    expect(circles).toHaveLength(2);
  });
});
