// lifted from ui/prototype/shell.jsx:5 (MmfpHeader)
// Server component. Two simplifications from the prototype:
//   - the product switcher is rendered as an inert chip — only one product
//     (MLI) exists today, so the dropdown has no targets. Chevron stays for
//     visual parity with the mockup.
//   - the repo link is non-functional ("#") because there is no canonical
//     external repo URL exposed to the UI yet.

import {
  IconBeaker,
  IconChevron,
  IconExternal,
  IconGit,
} from "./primitives/icons";
import type { Role } from "@/lib/roles";
import VersionBadge from "./VersionBadge";
import RoleBadge from "./RoleBadge";

export interface MmfpHeaderProduct {
  id: string;
  name: string;
}

interface MmfpHeaderProps {
  env: string;
  runId?: string;
  rubricVersion: string;
  product: MmfpHeaderProduct;
  role?: Role;
}

export default function MmfpHeader({
  env,
  runId,
  rubricVersion,
  product,
  role,
}: MmfpHeaderProps) {
  return (
    <header
      data-testid="app-shell-header"
      style={{
        height: 60,
        padding: "0 20px",
        borderBottom: "1px solid var(--neutral-11)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "#fff",
        flexShrink: 0,
        fontFamily: "var(--font-sans)",
        position: "relative",
        zIndex: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/morae-logo.svg"
          alt="Morae"
          style={{ height: 28, width: "auto" }}
        />
        <div style={{ width: 1, height: 22, background: "var(--neutral-10)" }} />
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: "var(--neutral-1)",
              letterSpacing: "-0.005em",
            }}
          >
            Model Fitness Platform
          </span>
          <VersionBadge initialVersion={rubricVersion} />
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexShrink: 0,
          whiteSpace: "nowrap",
        }}
      >
        {runId && (
          <span
            data-testid="run-id-chip"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              color: "var(--neutral-6)",
              fontFamily: "var(--font-mono)",
              whiteSpace: "nowrap",
            }}
          >
            <IconBeaker size={13} />
            {runId}
            <IconExternal size={11} color="var(--neutral-7)" />
          </span>
        )}
        {role && <RoleBadge role={role} />}
        <span
          data-testid="env-badge"
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "var(--neutral-3)",
            background: "var(--neutral-12)",
            padding: "3px 8px",
            borderRadius: 4,
            fontFamily: "var(--font-mono)",
            letterSpacing: 0.4,
          }}
        >
          {env.toUpperCase()}
        </span>

        {/* Product context. Inert today — see file header. */}
        <div style={{ position: "relative" }}>
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--neutral-7)",
              marginRight: 8,
            }}
          >
            Product
          </span>
          <span
            data-testid="product-chip"
            aria-disabled
            style={{
              height: 32,
              padding: "0 10px",
              borderRadius: 6,
              border: "1px solid var(--neutral-11)",
              background: "#fff",
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12,
              fontWeight: 500,
              color: "var(--neutral-2)",
              fontFamily: "inherit",
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background:
                  product.id === "mli" ? "var(--green)" : "var(--neutral-9)",
              }}
            />
            {product.name}
            <IconChevron size={12} />
          </span>
        </div>

        <div style={{ width: 1, height: 22, background: "var(--neutral-10)" }} />
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 12,
            color: "var(--neutral-3)",
            fontWeight: 500,
          }}
        >
          <IconGit size={14} /> morae-model-fitness
        </span>
      </div>
    </header>
  );
}