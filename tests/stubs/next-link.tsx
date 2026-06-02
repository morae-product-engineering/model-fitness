// MLI-196: vitest-only stub for `next/link`.
//
// next is only installed in ui/node_modules; root vitest resolves `next/link`
// to ui/node_modules/next which brings its own React instance, causing hook
// mismatch errors when rendering components that use <Link>.
// This stub provides a plain <a> so component tests can render without the
// Next.js router context. Tests that need to inspect link behaviour use the
// href prop directly on the rendered anchor.

import React from "react";

interface LinkProps {
  href: string;
  children?: React.ReactNode;
  [key: string]: unknown;
}

export default function Link({ href, children, ...rest }: LinkProps) {
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  );
}
