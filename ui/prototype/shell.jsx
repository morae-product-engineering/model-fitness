/* global React, MMFP_PRODUCTS, Btn, Chip, IconChevron, IconBeaker, IconGit, IconExternal */
const { useState: useShellState } = React;

// Header: Morae logo + product switcher (instead of tenant) + env + run id
function MmfpHeader({ product, onProduct, env = 'production', runId, rubricVersion = 'v0.1.4' }) {
  const [open, setOpen] = useShellState(false);
  return (
    <header style={{
      height: 60, padding: '0 20px',
      borderBottom: '1px solid var(--neutral-11)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: '#fff', flexShrink: 0, fontFamily: 'var(--font-sans)',
      position: 'relative', zIndex: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <img src="assets/morae-logo.svg" alt="Morae" style={{ height: 28, width: 'auto' }} />
        <div style={{ width: 1, height: 22, background: 'var(--neutral-10)' }} />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--neutral-1)', letterSpacing: '-0.005em' }}>
            Model Fitness Platform
          </span>
          <span style={{ fontSize: 11, color: 'var(--neutral-6)', fontFamily: 'var(--font-mono)' }}>{rubricVersion}</span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0, whiteSpace: 'nowrap' }}>
        {runId && (
          <a href="#" style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 11, color: 'var(--neutral-6)', fontFamily: 'var(--font-mono)',
            textDecoration: 'none', whiteSpace: 'nowrap',
          }}>
            <IconBeaker size={13} />
            {runId}
            <IconExternal size={11} color="var(--neutral-7)" />
          </a>
        )}
        <span style={{
          fontSize: 11, fontWeight: 600, color: 'var(--neutral-3)',
          background: 'var(--neutral-12)', padding: '3px 8px', borderRadius: 4,
          fontFamily: 'var(--font-mono)', letterSpacing: 0.4,
        }}>{env.toUpperCase()}</span>

        {/* product switcher */}
        <div style={{ position: 'relative' }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--neutral-7)', marginRight: 8 }}>Product</span>
          <button onClick={() => setOpen(o => !o)} style={{
            height: 32, padding: '0 10px', borderRadius: 6,
            border: '1px solid var(--neutral-11)', background: '#fff',
            display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 500,
            color: 'var(--neutral-2)', cursor: 'pointer', fontFamily: 'inherit',
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: product.id === 'mli' ? 'var(--green)' : 'var(--neutral-9)',
            }} />
            {product.name}
            <IconChevron size={12} />
          </button>
          {open && (
            <div style={{
              position: 'absolute', top: 38, right: 0, minWidth: 240,
              background: '#fff', border: '1px solid var(--neutral-11)', borderRadius: 8,
              boxShadow: 'var(--shadow-md)', padding: 4, zIndex: 50,
            }}>
              {MMFP_PRODUCTS.map(p => (
                <button key={p.id} onClick={() => { onProduct(p); setOpen(false); }}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '8px 10px', borderRadius: 4, background: p.id === product.id ? 'var(--neutral-12)' : 'transparent',
                    border: 'none', cursor: 'pointer',
                    fontSize: 13, color: 'var(--neutral-1)', textAlign: 'left',
                    opacity: p.status === 'soon' ? 0.6 : 1, fontFamily: 'inherit',
                  }}>
                  <div>
                    <div style={{ fontWeight: 500 }}>{p.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--neutral-6)', marginTop: 2 }}>{p.full}</div>
                  </div>
                  {p.status === 'soon' && <Chip tone="outline">not onboarded</Chip>}
                  {p.id === product.id && p.status === 'active' && <Chip tone="success">active</Chip>}
                </button>
              ))}
              <div style={{ borderTop: '1px solid var(--neutral-11)', marginTop: 4, paddingTop: 4 }}>
                <div style={{ padding: '6px 10px', fontSize: 11, color: 'var(--neutral-6)' }}>
                  Onboarding: <span style={{ fontFamily: 'var(--font-mono)' }}>morae-fitness init &lt;product&gt;</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div style={{ width: 1, height: 22, background: 'var(--neutral-10)' }} />
        <a href="#" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12,
          color: 'var(--neutral-3)', textDecoration: 'none', fontWeight: 500,
        }}>
          <IconGit size={14} /> morae-model-fitness
        </a>
      </div>
    </header>
  );
}

// Top tab nav
function TabNav({ active, onChange, items }) {
  return (
    <nav style={{
      background: '#fff',
      borderBottom: '1px solid var(--neutral-11)',
      padding: '0 20px',
      display: 'flex', alignItems: 'center', gap: 0, height: 44,
      fontFamily: 'var(--font-sans)', flexShrink: 0,
    }}>
      {items.map(it => {
        const isActive = active === it.id;
        return (
          <button key={it.id} onClick={() => onChange(it.id)} style={{
            position: 'relative', height: '100%', padding: '0 16px',
            background: 'transparent', border: 'none', cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: 8,
            fontFamily: 'inherit', fontSize: 13, fontWeight: isActive ? 600 : 500,
            color: isActive ? 'var(--neutral-1)' : 'var(--neutral-6)',
          }}>
            {it.label}
            {it.badge && (
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 8,
                background: it.badgeTone === 'warn' ? 'var(--light-yellow)' : 'var(--neutral-12)',
                color: it.badgeTone === 'warn' ? '#8a6600' : 'var(--neutral-5)',
                fontFamily: 'var(--font-mono)',
              }}>{it.badge}</span>
            )}
            {isActive && (
              <span style={{
                position: 'absolute', left: 12, right: 12, bottom: -1, height: 2,
                background: 'var(--neutral-1)', borderRadius: 2,
              }} />
            )}
          </button>
        );
      })}
    </nav>
  );
}

window.MmfpHeader = MmfpHeader;
window.TabNav = TabNav;
