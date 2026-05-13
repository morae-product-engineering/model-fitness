// lifted from ui/prototype/primitives.jsx:111 (Delta)
// Coloured ▲/▼ delta chip. Used in the Primary / Fallback slots of the
// portfolio summary (MLI-263) — composite score change versus the prior run.
// Null/undefined values render an em-dash so the slot still aligns.

interface DeltaProps {
  value: number | null | undefined;
  unit?: string;
  goodDirection?: "up" | "down";
  big?: boolean;
}

export default function Delta({
  value,
  unit = "",
  goodDirection = "up",
  big = false,
}: DeltaProps) {
  if (value == null || Number.isNaN(value)) {
    return <span style={{ color: "var(--neutral-7)" }}>—</span>;
  }
  const isPositive = value > 0;
  const isGood = goodDirection === "up" ? isPositive : !isPositive;
  if (Math.abs(value) < 0.05) {
    return (
      <span
        style={{
          color: "var(--neutral-6)",
          fontFamily: "var(--font-mono)",
          fontSize: big ? 13 : 11,
        }}
      >
        ±0{unit}
      </span>
    );
  }
  return (
    <span
      style={{
        color: isGood ? "var(--green)" : "var(--warm-red)",
        fontFamily: "var(--font-mono)",
        fontSize: big ? 13 : 11,
        fontWeight: 600,
      }}
    >
      {isPositive ? "▲" : "▼"} {isPositive ? "+" : ""}
      {value.toFixed(Math.abs(value) < 10 ? 1 : 0)}
      {unit}
    </span>
  );
}
