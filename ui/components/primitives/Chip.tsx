// lifted from ui/prototype/primitives.jsx:37 (Chip)
// Inline tones (object lookup) preserve the prototype's prop surface so other
// sub-tasks porting page bodies (MLI-263, MLI-264) can use this directly.

import type { CSSProperties, ReactNode } from "react";

export type ChipTone =
  | "neutral"
  | "info"
  | "success"
  | "warn"
  | "danger"
  | "ai"
  | "primary"
  | "outline";

interface ChipProps {
  tone?: ChipTone;
  children: ReactNode;
  style?: CSSProperties;
}

const TONES: Record<ChipTone, CSSProperties> = {
  neutral: { background: "var(--neutral-12)", color: "var(--neutral-3)" },
  info:    { background: "var(--light-blue)",   color: "var(--blue-2)" },
  success: { background: "var(--light-green)",  color: "var(--green)" },
  warn:    { background: "var(--light-yellow)", color: "#8a6600" },
  danger:  { background: "var(--light-red)",    color: "var(--warm-red)" },
  ai:      { background: "var(--light-purple)", color: "var(--purple)" },
  primary: { background: "var(--neutral-1)",    color: "#fff" },
  outline: {
    background: "#fff",
    color: "var(--neutral-3)",
    border: "1px solid var(--neutral-11)",
  },
};

export default function Chip({ tone = "neutral", children, style = {} }: ChipProps) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1.5,
        letterSpacing: 0.1,
        ...TONES[tone],
        ...style,
      }}
    >
      {children}
    </span>
  );
}
