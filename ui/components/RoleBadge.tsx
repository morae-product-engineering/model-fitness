"use client";

import { useRouter } from "next/navigation";
import { useTransition, useState, useRef, useEffect } from "react";
import { switchRole } from "@/lib/actions";
import type { Role } from "@/lib/roles";

const ROLES: Role[] = ["steward", "viewer"];

export default function RoleBadge({ role }: { role: Role }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const select = (next: Role) => {
    setOpen(false);
    if (next === role) return;
    startTransition(async () => {
      await switchRole(next);
      router.refresh();
    });
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        data-testid="role-badge"
        disabled={pending}
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          fontSize: 11,
          fontWeight: 600,
          color: role === "steward" ? "var(--neutral-2)" : "var(--neutral-5)",
          background:
            role === "steward" ? "var(--neutral-11)" : "var(--neutral-12)",
          padding: "3px 8px",
          borderRadius: 4,
          fontFamily: "var(--font-mono)",
          letterSpacing: 0.4,
          cursor: pending ? "default" : "pointer",
          border: "none",
          opacity: pending ? 0.5 : 1,
        }}
      >
        {role.toUpperCase()}
        <span style={{ fontSize: 9, opacity: 0.6 }}>▾</span>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            background: "#fff",
            border: "1px solid var(--neutral-11)",
            borderRadius: 6,
            boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            minWidth: 120,
            zIndex: 100,
            overflow: "hidden",
          }}
        >
          {ROLES.map((r) => {
            const isActive = r === role;
            return (
              <button
                key={r}
                onClick={() => select(r)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  width: "100%",
                  padding: "8px 12px",
                  fontSize: 12,
                  fontWeight: isActive ? 600 : 400,
                  fontFamily: "var(--font-mono)",
                  color: isActive ? "var(--neutral-1)" : "var(--neutral-3)",
                  background: isActive ? "var(--neutral-13)" : "#fff",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                  letterSpacing: 0.4,
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: isActive ? "var(--green)" : "transparent",
                    border: isActive ? "none" : "1.5px solid var(--neutral-10)",
                    flexShrink: 0,
                  }}
                />
                {r.toUpperCase()}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
