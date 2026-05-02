/* global React */
// ============================================================
// MMFP — Shared primitives
// ============================================================
const { useState, useMemo, useEffect, useRef } = React;

// — Button — matches MSI primitive
function Btn({ variant = 'default', size = 'default', icon, children, style = {}, ...p }) {
  const variants = {
    default:     { background: 'var(--neutral-1)', color: '#fff', border: '1px solid var(--neutral-1)' },
    secondary:   { background: 'var(--orange)',    color: 'var(--neutral-1)', border: '1px solid var(--orange)' },
    outline:     { background: '#fff',             color: 'var(--neutral-1)', border: '2px solid var(--neutral-11)' },
    ghost:       { background: 'transparent',      color: 'var(--neutral-1)', border: '1px solid transparent' },
    destructive: { background: 'var(--warm-red)',  color: '#fff', border: '1px solid var(--warm-red)' },
  };
  const sizes = {
    default: { height: 36, padding: '0 14px', fontSize: 13 },
    sm:      { height: 28, padding: '0 10px', fontSize: 12 },
    lg:      { height: 42, padding: '0 20px', fontSize: 14 },
    icon:    { height: 32, width: 32, padding: 0, justifyContent: 'center' },
  };
  return (
    <button {...p} style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
      borderRadius: 6, fontFamily: 'var(--font-sans)', fontWeight: 500,
      cursor: p.disabled ? 'not-allowed' : 'pointer', whiteSpace: 'nowrap',
      transition: 'all 150ms', opacity: p.disabled ? 0.5 : 1,
      ...variants[variant], ...sizes[size], ...style,
    }}>
      {icon}
      {children}
    </button>
  );
}

// — Badge —
function Chip({ tone = 'neutral', children, style = {} }) {
  const tones = {
    neutral: { background: 'var(--neutral-12)', color: 'var(--neutral-3)' },
    info:    { background: 'var(--light-blue)', color: 'var(--blue-2)' },
    success: { background: 'var(--light-green)', color: 'var(--green)' },
    warn:    { background: 'var(--light-yellow)', color: '#8a6600' },
    danger:  { background: 'var(--light-red)',  color: 'var(--warm-red)' },
    ai:      { background: 'var(--light-purple)', color: 'var(--purple)' },
    primary: { background: 'var(--neutral-1)',  color: '#fff' },
    outline: { background: '#fff', color: 'var(--neutral-3)', border: '1px solid var(--neutral-11)' },
  };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
      lineHeight: 1.5, letterSpacing: 0.1, ...tones[tone], ...style,
    }}>{children}</span>
  );
}

// — Card —
function Panel({ children, style = {}, padding = 20 }) {
  return (
    <div style={{
      background: '#fff', border: '1px solid var(--neutral-11)',
      borderRadius: 10, padding, boxShadow: 'var(--shadow-xs)',
      ...style,
    }}>{children}</div>
  );
}

function SectionHeader({ eyebrow, title, sub, right }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, marginBottom: 12 }}>
      <div>
        {eyebrow && <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 4 }}>{eyebrow}</div>}
        <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--neutral-1)', letterSpacing: '-0.005em' }}>{title}</div>
        {sub && <div style={{ fontSize: 13, color: 'var(--neutral-6)', marginTop: 2 }}>{sub}</div>}
      </div>
      {right}
    </div>
  );
}

// — Tier pill —
function TierPill({ tier, showName = false, colorOn = true }) {
  const accent = colorOn ? tier.accent : 'var(--neutral-4)';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 600,
      color: 'var(--neutral-2)',
    }}>
      <span style={{
        background: accent, color: colorOn && tier.id === 't1' ? 'var(--neutral-1)' : '#fff',
        padding: '2px 7px', borderRadius: 3, fontSize: 11, fontWeight: 700, letterSpacing: 0.4,
        fontFamily: 'var(--font-mono)',
      }}>{tier.code}</span>
      {showName && <span>{tier.name}</span>}
    </span>
  );
}

// — Tier rule (left bar accent stripe) —
function TierRule({ tier, colorOn = true, w = 3 }) {
  return (
    <div style={{
      width: w, alignSelf: 'stretch',
      background: colorOn ? tier.accent : 'var(--neutral-10)',
      borderRadius: 2,
    }} />
  );
}

// — Mini delta chip —
function Delta({ value, unit = '', goodDirection = 'up', big = false }) {
  if (value == null || isNaN(value)) return <span style={{ color: 'var(--neutral-7)' }}>—</span>;
  const isPositive = value > 0;
  const isGood = goodDirection === 'up' ? isPositive : !isPositive;
  if (Math.abs(value) < 0.05) {
    return <span style={{ color: 'var(--neutral-6)', fontFamily: 'var(--font-mono)', fontSize: big ? 13 : 11 }}>±0{unit}</span>;
  }
  return (
    <span style={{
      color: isGood ? 'var(--green)' : 'var(--warm-red)',
      fontFamily: 'var(--font-mono)', fontSize: big ? 13 : 11, fontWeight: 600,
    }}>
      {isPositive ? '▲' : '▼'} {isPositive ? '+' : ''}{value.toFixed(Math.abs(value) < 10 ? 1 : 0)}{unit}
    </span>
  );
}

// — Sparkline —
function Spark({ data, w = 80, h = 26, stroke = 'var(--neutral-3)', fill = 'none' }) {
  const pts = data.filter(v => v != null);
  if (pts.length < 2) return <svg width={w} height={h} />;
  const min = Math.min(...pts), max = Math.max(...pts);
  const range = max - min || 1;
  const xs = data.map((_, i) => (i / (data.length - 1)) * w);
  const ys = data.map(v => v == null ? null : h - ((v - min) / range) * (h - 4) - 2);
  const path = data.map((v, i) => {
    if (v == null) return '';
    return (i === 0 || data[i - 1] == null ? 'M' : 'L') + xs[i].toFixed(1) + ' ' + ys[i].toFixed(1);
  }).join(' ');
  return (
    <svg width={w} height={h} style={{ overflow: 'visible' }}>
      <path d={path} fill={fill} stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {data.map((v, i) => v != null ? <circle key={i} cx={xs[i]} cy={ys[i]} r={i === data.length - 1 ? 2.5 : 0} fill={stroke} /> : null)}
    </svg>
  );
}

// — Modal —
function Modal({ open, onClose, title, children, width = 720 }) {
  if (!open) return null;
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(13,13,13,0.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      padding: 24,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: '#fff', borderRadius: 12, width, maxWidth: '100%', maxHeight: '90vh',
        display: 'flex', flexDirection: 'column', boxShadow: 'var(--shadow-lg)',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--neutral-11)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>{title}</div>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--neutral-6)', fontSize: 20, padding: 4, lineHeight: 1,
          }}>×</button>
        </div>
        <div style={{ overflow: 'auto', padding: 20 }}>{children}</div>
      </div>
    </div>
  );
}

// — Toast —
function Toast({ message, onDismiss }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onDismiss, 2400);
    return () => clearTimeout(t);
  }, [message]);
  if (!message) return null;
  return (
    <div style={{
      position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
      background: 'var(--neutral-1)', color: '#fff', padding: '10px 16px',
      borderRadius: 8, fontSize: 13, fontWeight: 500, zIndex: 200,
      boxShadow: 'var(--shadow-md)',
    }}>{message}</div>
  );
}

// — Lucide-ish icons (minimal inline SVG) —
const IconStroke = (path, viewBox = '0 0 24 24') => ({ size = 16, color = 'currentColor', style = {} }) => (
  <svg width={size} height={size} viewBox={viewBox} fill="none" stroke={color}
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={style}>
    {path}
  </svg>
);
const IconCheck    = IconStroke(<polyline points="20 6 9 17 4 12" />);
const IconX        = IconStroke(<><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>);
const IconChevron  = IconStroke(<polyline points="6 9 12 15 18 9" />);
const IconChevronR = IconStroke(<polyline points="9 18 15 12 9 6" />);
const IconAlert    = IconStroke(<><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12" y2="17" /></>);
const IconInfo     = IconStroke(<><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="8" /></>);
const IconDownload = IconStroke(<><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></>);
const IconLink     = IconStroke(<><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></>);
const IconPlay     = IconStroke(<polygon points="5 3 19 12 5 21 5 3" />);
const IconGit      = IconStroke(<><circle cx="18" cy="18" r="3" /><circle cx="6" cy="6" r="3" /><path d="M13 6h3a2 2 0 0 1 2 2v7" /><line x1="6" y1="9" x2="6" y2="21" /></>);
const IconFilter   = IconStroke(<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />);
const IconPlus     = IconStroke(<><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>);
const IconLock     = IconStroke(<><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></>);
const IconSearch   = IconStroke(<><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></>);
const IconRefresh  = IconStroke(<><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10" /><path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14" /></>);
const IconTrend    = IconStroke(<><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></>);
const IconBeaker   = IconStroke(<><path d="M9 3h6v5l5 9a2 2 0 0 1-1.8 3H5.8A2 2 0 0 1 4 17l5-9V3z" /><line x1="6.5" y1="13" x2="17.5" y2="13" /></>);
const IconExternal = IconStroke(<><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></>);

Object.assign(window, {
  Btn, Chip, Panel, SectionHeader, TierPill, TierRule, Delta, Spark, Modal, Toast,
  IconCheck, IconX, IconChevron, IconChevronR, IconAlert, IconInfo, IconDownload,
  IconLink, IconPlay, IconGit, IconFilter, IconPlus, IconLock, IconSearch, IconRefresh,
  IconTrend, IconBeaker, IconExternal,
});
