// lifted from ui/prototype/primitives.jsx:197 (IconStroke + icon set)
// Only the icons the shell actually uses are ported here; the rest are
// deferred to whichever sub-task first needs them.

import type { CSSProperties, ReactNode } from "react";

interface IconProps {
  size?: number;
  color?: string;
  style?: CSSProperties;
}

function stroke(path: ReactNode, viewBox = "0 0 24 24") {
  return function Icon({ size = 16, color = "currentColor", style = {} }: IconProps) {
    return (
      <svg
        width={size}
        height={size}
        viewBox={viewBox}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={style}
        aria-hidden
      >
        {path}
      </svg>
    );
  };
}

export const IconChevron = stroke(<polyline points="6 9 12 15 18 9" />);
export const IconBeaker = stroke(
  <>
    <path d="M9 3h6v5l5 9a2 2 0 0 1-1.8 3H5.8A2 2 0 0 1 4 17l5-9V3z" />
    <line x1="6.5" y1="13" x2="17.5" y2="13" />
  </>,
);
export const IconGit = stroke(
  <>
    <circle cx="18" cy="18" r="3" />
    <circle cx="6" cy="6" r="3" />
    <path d="M13 6h3a2 2 0 0 1 2 2v7" />
    <line x1="6" y1="9" x2="6" y2="21" />
  </>,
);
export const IconExternal = stroke(
  <>
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </>,
);
