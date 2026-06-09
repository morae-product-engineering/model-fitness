// lifted from ui/prototype/shell.jsx:105 (TabNav)
// All four tabs are now navigable: Scoreboard, Editor, Curator, and History.

import Link from "next/link";
import type { Role } from "@/lib/roles";

export type TabId = "scoreboard" | "editor" | "curator" | "history";

interface TabSpec {
  id: TabId;
  label: string;
  href?: string;
}

const TABS: TabSpec[] = [
  { id: "scoreboard", label: "Scoreboard", href: "/scoreboard?product=mli" },
  { id: "editor", label: "Editor", href: "/editor?product=mli" },
  { id: "curator", label: "Curator", href: "/curator?product=mli" },
  { id: "history", label: "History", href: "/history?product=mli" },
];

const STEWARD_ONLY = new Set<TabId>(["editor", "curator"]);

interface TabNavProps {
  activeTab: TabId;
  role?: Role;
}

export default function TabNav({ activeTab, role }: TabNavProps) {
  const visibleTabs =
    role === "viewer" ? TABS.filter((tab) => !STEWARD_ONLY.has(tab.id)) : TABS;

  return (
    <nav
      data-testid="app-shell-tabs"
      style={{
        background: "#fff",
        borderBottom: "1px solid var(--neutral-11)",
        padding: "0 20px",
        display: "flex",
        alignItems: "center",
        gap: 0,
        height: 44,
        fontFamily: "var(--font-sans)",
        flexShrink: 0,
      }}
    >
      {visibleTabs.map((tab) => {
        const isActive = tab.id === activeTab;
        const enabled = Boolean(tab.href);

        const inner = (
          <span
            style={{
              position: "relative",
              height: "100%",
              padding: "0 16px",
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              fontFamily: "inherit",
              fontSize: 13,
              fontWeight: isActive ? 600 : 500,
              color: isActive
                ? "var(--neutral-1)"
                : enabled
                  ? "var(--neutral-6)"
                  : "var(--neutral-9)",
              cursor: enabled ? "pointer" : "not-allowed",
            }}
          >
            {tab.label}
            {isActive && (
              <span
                style={{
                  position: "absolute",
                  left: 12,
                  right: 12,
                  bottom: -1,
                  height: 2,
                  background: "var(--neutral-1)",
                  borderRadius: 2,
                }}
              />
            )}
          </span>
        );

        return enabled ? (
          <Link
            key={tab.id}
            href={tab.href!}
            data-testid={`tab-${tab.id}`}
            data-active={isActive ? "true" : "false"}
            style={{
              height: "100%",
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "stretch",
            }}
          >
            {inner}
          </Link>
        ) : (
          <span
            key={tab.id}
            data-testid={`tab-${tab.id}`}
            data-active="false"
            data-disabled="true"
            title="Available in a later slice"
            aria-disabled
            style={{
              height: "100%",
              display: "inline-flex",
              alignItems: "stretch",
            }}
          >
            {inner}
          </span>
        );
      })}
    </nav>
  );
}
