/* global React, MMFP_TIERS, MMFP_CANDIDATES, Btn, Chip, Panel, TierPill,
   IconCheck, IconX, IconAlert, IconGit, IconExternal, IconLock */

function candByIdH(id) { return MMFP_CANDIDATES.find(c => c.id === id); }
function tierById(id)  { return MMFP_TIERS.find(t => t.id === id); }

function History({ history, product, colorOn }) {
  // Group by date (yyyy-mm-dd)
  const byDay = {};
  for (const e of history) {
    const day = e.at.slice(0, 10);
    (byDay[day] ||= []).push(e);
  }
  const days = Object.keys(byDay).sort().reverse();

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase' }}>
          History · {product.name}
        </div>
        <h1 style={{ margin: '6px 0 4px', fontSize: 26, letterSpacing: '-0.01em' }}>Audit trail</h1>
        <div style={{ fontSize: 13, color: 'var(--neutral-6)' }}>
          Every rubric save and portfolio decision, with actor, run reference, and rationale. Chronological — newest first.
        </div>
      </div>

      <Panel style={{ padding: 0 }}>
        {days.length === 0 && (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--neutral-6)', fontSize: 13 }}>
            No history yet. Save a rubric edit or make a portfolio decision to populate this view.
          </div>
        )}
        {days.map((day, di) => (
          <div key={day} style={{ borderTop: di === 0 ? 'none' : '1px solid var(--neutral-11)' }}>
            <div style={{
              padding: '10px 18px', background: 'var(--neutral-13)',
              fontSize: 11, fontWeight: 600, color: 'var(--neutral-5)',
              letterSpacing: 0.4, textTransform: 'uppercase',
              fontFamily: 'var(--font-mono)',
              borderBottom: '1px solid var(--neutral-11)',
            }}>
              {day}
            </div>
            {byDay[day].map(e => <HistoryEntry key={e.id} entry={e} colorOn={colorOn} />)}
          </div>
        ))}
      </Panel>

      <div style={{ marginTop: 18, fontSize: 11, color: 'var(--neutral-6)', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
        Audit log queryable via API · separate retention policy · synced to <a href="#">Confluence governance space</a>
      </div>
    </div>
  );
}

function HistoryEntry({ entry, colorOn }) {
  const tier = entry.tier ? tierById(entry.tier) : null;
  const cand = entry.candidate ? candByIdH(entry.candidate) : null;
  const time = entry.at.slice(11);

  let icon, kindLabel, kindTone;
  if (entry.kind === 'rubric_save') {
    icon = <IconGit size={14} color="var(--blue-2)" />;
    kindLabel = 'Rubric saved';
    kindTone = { background: 'var(--light-blue)', color: 'var(--blue-2)' };
  } else if (entry.kind === 'promote') {
    icon = <IconCheck size={14} color="var(--green)" />;
    kindLabel = entry.toRole === 'primary' ? 'Promoted to Primary' : 'Set as Fallback';
    kindTone = { background: 'var(--light-green)', color: 'var(--green)' };
  } else if (entry.kind === 'reject') {
    icon = <IconX size={14} color="var(--warm-red)" />;
    kindLabel = 'Rejected';
    kindTone = { background: 'var(--light-red)', color: 'var(--warm-red)' };
  } else if (entry.kind === 'reinstate') {
    icon = <IconAlert size={14} color="#8a6600" />;
    kindLabel = 'Reinstated';
    kindTone = { background: 'var(--light-yellow)', color: '#8a6600' };
  }

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '90px 1fr', gap: 18,
      padding: '14px 18px', borderBottom: '1px solid var(--neutral-12)',
    }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--neutral-6)' }}>{time}</div>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 4,
            ...kindTone,
          }}>
            {icon}{kindLabel}
          </span>
          {tier && <TierPill tier={tier} colorOn={colorOn} />}
          {cand && (
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--neutral-1)' }}>
              {cand.name} <span style={{ fontWeight: 400, color: 'var(--neutral-6)' }}>· {cand.vendor}</span>
            </span>
          )}
          {entry.version && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--neutral-3)', background: 'var(--neutral-12)', padding: '2px 6px', borderRadius: 4 }}>
              {entry.version}
            </span>
          )}
        </div>
        {(entry.rationale || entry.note) && (
          <div style={{ fontSize: 13, color: 'var(--neutral-2)', marginTop: 6, lineHeight: 1.5 }}>
            “{entry.rationale || entry.note}”
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6, fontSize: 11, color: 'var(--neutral-6)', flexWrap: 'wrap' }}>
          <span>by <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--neutral-3)' }}>{entry.actor}</span></span>
          {entry.runId && (
            <a href="#" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontFamily: 'var(--font-mono)' }}>
              {entry.runId} <IconExternal size={10} />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

window.History = History;
