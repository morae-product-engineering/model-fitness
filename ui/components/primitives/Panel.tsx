// lifted from ui/prototype/primitives.jsx:58 (Panel)
// Bordered surface with optional inline padding override. Used by tier cards
// and inner score-detail panels; preserved here so other ports can drop in.

import type { CSSProperties, ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  style?: CSSProperties;
  padding?: number | string;
}

export default function Panel({ children, style = {}, padding = 20 }: PanelProps) {
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid var(--neutral-11)",
        borderRadius: 10,
        padding,
        boxShadow: "var(--shadow-xs)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
