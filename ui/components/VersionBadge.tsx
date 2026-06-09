"use client";

// Client component wrapper for the rubric-version display so it can update
// immediately (in the same React render as the save toast) when a steward
// saves the rubric, without waiting for router.refresh() to complete.
// RubricEditor dispatches a "rubric-saved" CustomEvent with { version } after
// a successful PUT; this component listens and updates the displayed version.

import { useEffect, useState } from "react";

export default function VersionBadge({ initialVersion }: { initialVersion: string }) {
  const [version, setVersion] = useState(initialVersion);

  useEffect(() => {
    const handler = (e: Event) => {
      setVersion((e as CustomEvent<{ version: string }>).detail.version);
    };
    window.addEventListener("rubric-saved", handler);
    return () => window.removeEventListener("rubric-saved", handler);
  }, []);

  return (
    <span
      data-testid="rubric-version"
      style={{
        fontSize: 11,
        color: "var(--neutral-6)",
        fontFamily: "var(--font-mono)",
      }}
    >
      {version}
    </span>
  );
}
