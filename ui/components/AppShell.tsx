// Composes the prototype's shell chrome (ui/prototype/shell.jsx) over the
// page body. Header (MmfpHeader) + tab nav (TabNav) sit above {children};
// the previous page-level eyebrow/h1/subtitle is superseded by the chrome.

import MmfpHeader, { type MmfpHeaderProduct } from "./MmfpHeader";
import TabNav, { type TabId } from "./TabNav";

interface AppShellProps {
  env: string;
  runId?: string;
  rubricVersion: string;
  product: MmfpHeaderProduct;
  activeTab: TabId;
  children: React.ReactNode;
}

export default function AppShell({
  env,
  runId,
  rubricVersion,
  product,
  activeTab,
  children,
}: AppShellProps) {
  return (
    <div
      data-testid="app-shell"
      className="min-h-screen flex flex-col font-sans"
      style={{ background: "var(--neutral-13)" }}
    >
      <MmfpHeader
        env={env}
        runId={runId}
        rubricVersion={rubricVersion}
        product={product}
      />
      <TabNav activeTab={activeTab} />
      <main className="flex-1">{children}</main>
    </div>
  );
}
