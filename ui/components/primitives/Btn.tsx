// lifted from ui/prototype/primitives.jsx:8 (Btn)
// Variants and sizes mirror the prototype. The shell doesn't currently use Btn
// directly but it pairs with Chip and sibling sub-tasks (MLI-263, MLI-264) will
// reach for it; porting it now means they don't have to.

import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";

export type BtnVariant = "default" | "secondary" | "outline" | "ghost" | "destructive";
export type BtnSize = "default" | "sm" | "lg" | "icon";

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BtnVariant;
  size?: BtnSize;
  icon?: ReactNode;
  children?: ReactNode;
  style?: CSSProperties;
}

const VARIANTS: Record<BtnVariant, CSSProperties> = {
  default:     { background: "var(--neutral-1)", color: "#fff", border: "1px solid var(--neutral-1)" },
  secondary:   { background: "var(--orange)",    color: "var(--neutral-1)", border: "1px solid var(--orange)" },
  outline:     { background: "#fff",             color: "var(--neutral-1)", border: "2px solid var(--neutral-11)" },
  ghost:       { background: "transparent",      color: "var(--neutral-1)", border: "1px solid transparent" },
  destructive: { background: "var(--warm-red)",  color: "#fff", border: "1px solid var(--warm-red)" },
};

const SIZES: Record<BtnSize, CSSProperties> = {
  default: { height: 36, padding: "0 14px", fontSize: 13 },
  sm:      { height: 28, padding: "0 10px", fontSize: 12 },
  lg:      { height: 42, padding: "0 20px", fontSize: 14 },
  icon:    { height: 32, width: 32, padding: 0, justifyContent: "center" },
};

export default function Btn({
  variant = "default",
  size = "default",
  icon,
  children,
  style = {},
  disabled,
  ...rest
}: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        borderRadius: 6,
        fontFamily: "var(--font-sans)",
        fontWeight: 500,
        cursor: disabled ? "not-allowed" : "pointer",
        whiteSpace: "nowrap",
        transition: "all 150ms",
        opacity: disabled ? 0.5 : 1,
        ...VARIANTS[variant],
        ...SIZES[size],
        ...style,
      }}
    >
      {icon}
      {children}
    </button>
  );
}
