// lifted from ui/prototype/primitives.jsx:128-146 (Spark)
// Mini sparkline primitive. Nulls in `data` break the path and restart with
// a new M, so gaps are preserved. Renders a 2.5px dot at the last non-null
// point. Returns a fixed-size empty SVG when fewer than 2 non-null points
// exist so callers never need to guard.

interface SparkProps {
  data: (number | null)[];
  w?: number;
  h?: number;
  stroke?: string;
  fill?: string;
}

export default function Spark({
  data,
  w = 80,
  h = 26,
  stroke = "var(--neutral-3)",
  fill = "none",
}: SparkProps) {
  const pts = data.filter((v) => v != null) as number[];
  if (pts.length < 2) return <svg width={w} height={h} />;

  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const range = max - min || 1;

  const xs = data.map((_, i) => (i / (data.length - 1)) * w);
  const ys = data.map((v) =>
    v == null ? null : h - ((v - min) / range) * (h - 4) - 2,
  );

  // Gap-handling: null values break the path; restart with M after a gap.
  const path = data
    .map((v, i) => {
      if (v == null) return "";
      return (i === 0 || data[i - 1] == null ? "M" : "L") +
        xs[i].toFixed(1) +
        " " +
        ys[i]!.toFixed(1);
    })
    .join(" ");

  return (
    <svg width={w} height={h} style={{ overflow: "visible" }}>
      <path
        d={path}
        fill={fill}
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {data.map((v, i) =>
        v != null ? (
          <circle
            key={i}
            cx={xs[i]}
            cy={ys[i]!}
            r={i === data.length - 1 ? 2.5 : 0}
            fill={stroke}
          />
        ) : null,
      )}
    </svg>
  );
}
