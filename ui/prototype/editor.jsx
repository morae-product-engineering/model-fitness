/* global React, MMFP_TIERS, MMFP_CANDIDATES, MMFP_RUNS, MMFP_DIMENSIONS, MMFP_LATEST_RUN,
   Btn, Chip, Panel, SectionHeader, TierPill, TierRule, Delta, Modal,
   IconCheck, IconX, IconChevron, IconChevronR, IconAlert, IconInfo,
   IconLock, IconPlay, IconGit, IconRefresh, IconBeaker, IconExternal */
const { useState: useEdState, useMemo: useEdMemo } = React;

function candByIdEd(id) { return MMFP_CANDIDATES.find(c => c.id === id); }

function compositeEd(rawDims, rubric) {
  const enabled = rubric.filter(d => d.enabled);
  const totalW = enabled.reduce((s, d) => s + d.weight, 0) || 1;
  let score = 0;
  for (const d of enabled) {
    const v = rawDims[d.id]; if (v == null) continue;
    score += (normalizeEd(v, d) * d.weight) / totalW;
  }
  return score;
}
function normalizeEd(v, d) {
  if (d.unit === '%' || d.unit === 'F1') return d.unit === 'F1' ? v * 100 : v;
  if (d.unit === '/5') return (v / 5) * 100;
  if (d.unit === 'ms') return Math.max(0, 100 - (v / 20));
  if (d.unit === 's')  return Math.max(0, 100 - v * 8);
  if (d.unit === '¢')  return Math.max(0, 100 - v * 8);
  return v;
}
function gateStatusEd(rawDims, rubric) {
  const failed = [];
  for (const d of rubric) {
    if (!d.enabled || !d.gate) continue;
    const v = rawDims[d.id]; if (v == null) continue;
    if (!checkGateEd(v, d)) failed.push(d.id);
  }
  return { passed: failed.length === 0, failed };
}
function checkGateEd(v, d) {
  const gt = (d.gateText || '').toLowerCase();
  if (gt.includes('≥') || gt.includes('>=')) { const n = parseFloat(gt.match(/[\d.]+/)?.[0] || '0'); return v >= n; }
  if (gt.includes('≤') || gt.includes('<=')) { const n = parseFloat(gt.match(/[\d.]+/)?.[0] || '999999'); return v <= n; }
  if (gt.includes('<')) { const n = parseFloat(gt.match(/[\d.]+/)?.[0] || '999999'); return v < n; }
  if (gt.includes('100')) return v >= 100;
  if (gt.includes('0')) return v <= 0.5;
  return true;
}
function rankingsEd(tier, rubric) {
  const runs = MMFP_RUNS[tier.id];
  return Object.entries(runs).map(([cid, r]) => ({
    cid, cand: candByIdEd(cid),
    composite: compositeEd(r.dims, rubric),
    gates: gateStatusEd(r.dims, rubric),
    origScore: r.composite,
  })).sort((a, b) => {
    if (a.gates.passed !== b.gates.passed) return a.gates.passed ? -1 : 1;
    return b.composite - a.composite;
  });
}

// ——— Weight slider row ———
function WeightRow({ dim, total, onChange, onToggle, mode }) {
  const isOver = total !== 100;
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '24px 1fr 56px 60px',
      gap: 10, alignItems: 'center', padding: '8px 0',
      borderBottom: '1px solid var(--neutral-12)',
      opacity: dim.enabled ? 1 : 0.45,
    }}>
      <input type="checkbox" checked={dim.enabled} onChange={onToggle}
             style={{ width: 14, height: 14, accentColor: 'var(--neutral-1)', cursor: 'pointer' }}
             disabled={mode === 'view'} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--neutral-1)', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {dim.label}
          {dim.gate && (
            <span title={`Gate: ${dim.gateText}`} style={{
              display: 'inline-flex', alignItems: 'center', gap: 3,
              fontSize: 10, padding: '1px 5px', borderRadius: 3,
              background: 'var(--neutral-12)', color: 'var(--neutral-5)', fontWeight: 600,
              fontFamily: 'var(--font-mono)',
            }}>
              <IconLock size={9} color="var(--neutral-5)" /> {dim.gateText}
            </span>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--neutral-6)', marginTop: 2 }}>{dim.desc}</div>
      </div>
      <input type="range" min={0} max={50} step={1} value={dim.weight} onChange={e => onChange(parseInt(e.target.value, 10))}
             disabled={mode === 'view' || !dim.enabled}
             style={{
               width: '100%', accentColor: isOver ? 'var(--warm-red)' : 'var(--neutral-1)',
               cursor: mode === 'view' ? 'not-allowed' : 'pointer',
             }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end' }}>
        <input type="number" min={0} max={100} value={dim.weight} disabled={mode === 'view' || !dim.enabled}
          onChange={e => onChange(parseInt(e.target.value || '0', 10))}
          style={{
            width: 44, height: 26, padding: '0 4px',
            border: '1px solid var(--neutral-10)', borderRadius: 4,
            fontSize: 12, textAlign: 'right', fontFamily: 'var(--font-mono)',
            color: 'var(--neutral-1)', background: '#fff',
          }} />
        <span style={{ fontSize: 11, color: 'var(--neutral-6)' }}>%</span>
      </div>
    </div>
  );
}

function RubricCard({ title, rubric, mode, badge, onChange }) {
  const total = rubric.filter(d => d.enabled).reduce((s, d) => s + d.weight, 0);
  const isOk = total === 100;
  const update = (idx, patch) => onChange(rubric.map((d, i) => i === idx ? { ...d, ...patch } : d));
  return (
    <Panel padding={0} style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{
        padding: '14px 16px', borderBottom: '1px solid var(--neutral-11)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: mode === 'view' ? 'var(--neutral-13)' : '#fff', flexWrap: 'wrap', gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--neutral-1)' }}>{title}</span>
          {badge}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 11, color: 'var(--neutral-6)' }}>Σ weights</span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
            color: isOk ? 'var(--green)' : 'var(--warm-red)',
            background: isOk ? 'var(--light-green)' : 'var(--light-red)',
            padding: '2px 8px', borderRadius: 4,
          }}>{total}%</span>
        </div>
      </div>
      <div style={{ padding: '4px 16px 12px' }}>
        {rubric.map((d, i) => (
          <WeightRow key={d.id} dim={d} total={total} mode={mode}
                     onChange={v => update(i, { weight: v })}
                     onToggle={() => update(i, { enabled: !d.enabled })} />
        ))}
      </div>
    </Panel>
  );
}

// — Live impact comparison (Current vs Edited) —
function LiveCompare({ tier, currentRubric, editedRubric, colorOn }) {
  const cur  = useEdMemo(() => rankingsEd(tier, currentRubric), [tier.id, currentRubric]);
  const prop = useEdMemo(() => rankingsEd(tier, editedRubric),  [tier.id, editedRubric]);
  const curRanks = Object.fromEntries(cur.map((r, i) => [r.cid, i]));
  const curScores = Object.fromEntries(cur.map(r => [r.cid, r.composite]));

  const newlyRejected = prop.filter(r => !r.gates.passed).map(r => r.cid)
    .filter(cid => cur.find(c => c.cid === cid)?.gates.passed);
  const newlyEligible = prop.filter(r => r.gates.passed).map(r => r.cid)
    .filter(cid => !cur.find(c => c.cid === cid)?.gates.passed);
  const rankShifts = prop.map((r, newIdx) => ({
    cid: r.cid, name: r.cand.name, delta: curRanks[r.cid] - newIdx,
  })).filter(s => Math.abs(s.delta) >= 1).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  const accent = colorOn ? tier.accent : 'var(--neutral-4)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0, background: '#fff', border: '1px solid var(--neutral-11)', borderRadius: 10, overflow: 'hidden' }}>
        <SummaryStat label="Rank shifts" value={rankShifts.length} sub={rankShifts.length ? `${rankShifts[0].name} ${rankShifts[0].delta > 0 ? '↑' : '↓'}${Math.abs(rankShifts[0].delta)}` : 'none'} />
        <SummaryStat label="New gate fails" value={newlyRejected.length} tone={newlyRejected.length ? 'warn' : 'ok'} sub={newlyRejected.length ? newlyRejected.map(c => candByIdEd(c).name).join(', ') : 'none'} />
        <SummaryStat label="Newly eligible" value={newlyEligible.length} tone={newlyEligible.length ? 'good' : 'ok'} sub={newlyEligible.length ? newlyEligible.map(c => candByIdEd(c).name).join(', ') : 'none'} />
        <SummaryStat label="New T-leader" value={prop[0].cid !== cur[0].cid ? '⚠ changed' : 'unchanged'}
                     tone={prop[0].cid !== cur[0].cid ? 'warn' : 'ok'}
                     sub={`${prop[0].cand.name} (${prop[0].composite.toFixed(1)})`} />
      </div>

      <Panel padding={0}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', borderBottom: '1px solid var(--neutral-11)' }}>
          <div style={{ padding: '10px 16px', borderRight: '1px solid var(--neutral-11)' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase' }}>
              Current · {tier.code}
            </div>
          </div>
          <div style={{ padding: '10px 16px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: accent, letterSpacing: 0.4, textTransform: 'uppercase' }}>
              Edited · {tier.code}
            </div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          <RankingList rows={cur}  side="current" />
          <RankingList rows={prop} side="edited" curRanks={curRanks} curScores={curScores} />
        </div>
      </Panel>
    </div>
  );
}

function SummaryStat({ label, value, sub, tone = 'neutral' }) {
  const tones = {
    ok:   { color: 'var(--neutral-1)' },
    good: { color: 'var(--green)' },
    warn: { color: 'var(--warm-red)' },
    neutral: { color: 'var(--neutral-1)' },
  };
  return (
    <div style={{ padding: '12px 16px', borderRight: '1px solid var(--neutral-11)' }}>
      <div style={{ fontSize: 11, color: 'var(--neutral-6)', fontWeight: 600, letterSpacing: 0.4, textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 600, marginTop: 4, letterSpacing: '-0.01em', ...tones[tone] }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--neutral-6)', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub}</div>
    </div>
  );
}

function RankingList({ rows, side, curRanks, curScores }) {
  return (
    <div style={{ borderRight: side === 'current' ? '1px solid var(--neutral-11)' : 'none' }}>
      {rows.map((r, i) => {
        let shift = 0, scoreDelta = 0;
        if (side === 'edited' && curRanks) {
          shift = curRanks[r.cid] - i;
          scoreDelta = r.composite - curScores[r.cid];
        }
        const failed = !r.gates.passed;
        return (
          <div key={r.cid} style={{
            display: 'grid', gridTemplateColumns: '24px 1fr auto auto',
            gap: 10, alignItems: 'center', padding: '8px 16px',
            borderBottom: '1px solid var(--neutral-12)',
            background: failed ? 'rgba(217,52,23,0.04)' : 'transparent',
          }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--neutral-6)' }}>{i + 1}</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: failed ? 'var(--warm-red)' : 'var(--neutral-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {r.cand.name}
                {failed && <IconLock size={10} color="var(--warm-red)" style={{ marginLeft: 4, verticalAlign: 'middle' }} />}
              </div>
              <div style={{ fontSize: 10, color: 'var(--neutral-6)' }}>
                {r.cand.vendor} · {r.cand.binding}
                {failed && r.gates.failed.length > 0 && (
                  <span style={{ color: 'var(--warm-red)', marginLeft: 6 }}>
                    fails: {r.gates.failed.join(', ')}
                  </span>
                )}
              </div>
            </div>
            {side === 'edited' && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
                             color: shift > 0 ? 'var(--green)' : shift < 0 ? 'var(--warm-red)' : 'var(--neutral-7)' }}>
                {shift > 0 ? '↑' : shift < 0 ? '↓' : '·'}{shift !== 0 ? Math.abs(shift) : ''}
              </span>
            )}
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--neutral-1)' }}>
              {r.composite.toFixed(1)}
              {side === 'edited' && Math.abs(scoreDelta) > 0.1 && (
                <span style={{ marginLeft: 6, fontWeight: 500, color: scoreDelta > 0 ? 'var(--green)' : 'var(--warm-red)' }}>
                  {scoreDelta > 0 ? '+' : ''}{scoreDelta.toFixed(1)}
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ——— Main Editor page ———
function Editor({ tweaks, setToast, product, rubricVersion, onSave }) {
  const [tierId, setTierId] = useEdState('t2');
  const tier = MMFP_TIERS.find(t => t.id === tierId);
  const colorOn = tweaks.colorOn;

  const [edited, setEdited] = useEdState(() =>
    Object.fromEntries(MMFP_TIERS.map(t => [t.id, MMFP_DIMENSIONS[t.id].map(d => ({ ...d }))]))
  );
  const currentRubric = MMFP_DIMENSIONS[tierId];
  const editedRubric = edited[tierId];

  const sig = useEdMemo(() => editedRubric.map(d => `${d.id}:${d.weight}:${d.enabled}`).join('|'), [editedRubric]);
  const isDirty = sig !== currentRubric.map(d => `${d.id}:${d.weight}:${d.enabled}`).join('|');

  function setEditedRubric(newR) { setEdited(p => ({ ...p, [tierId]: newR })); }
  function reset() { setEdited(p => ({ ...p, [tierId]: MMFP_DIMENSIONS[tierId].map(d => ({ ...d })) })); }

  const totalEd = editedRubric.filter(d => d.enabled).reduce((s, d) => s + d.weight, 0);
  const canSave = totalEd === 100 && isDirty;

  const [showSave, setShowSave] = useEdState(false);
  const [note, setNote] = useEdState('');
  const [saving, setSaving] = useEdState(false);

  function nextVersion(v) {
    const m = v.match(/^v?(\d+)\.(\d+)\.(\d+)$/);
    if (!m) return v + '.1';
    return `v${m[1]}.${m[2]}.${parseInt(m[3], 10) + 1}`;
  }

  function commitSave() {
    setSaving(true);
    setTimeout(() => {
      const newVer = nextVersion(rubricVersion);
      onSave({
        version: newVer, tier: tierId, note,
        rubric: editedRubric.map(d => ({ ...d })),
      });
      setSaving(false);
      setShowSave(false);
      setNote('');
      // sync the "current" baseline by mutating in-memory dimensions
      MMFP_DIMENSIONS[tierId] = editedRubric.map(d => ({ ...d }));
      // refresh edited state to clean
      setEdited(p => ({ ...p, [tierId]: MMFP_DIMENSIONS[tierId].map(d => ({ ...d })) }));
      setToast(`Saved rubric ${newVer} for ${tier.code}. Re-scoring queued.`);
    }, 900);
  }

  return (
    <div style={{ padding: 24, maxWidth: 1480, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 16, gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase' }}>
            Editor · {product.name} · live impact
          </div>
          <h1 style={{ margin: '6px 0 4px', fontSize: 26, letterSpacing: '-0.01em' }}>
            Rubric · {tier.code} · {tier.name}
          </h1>
          <div style={{ fontSize: 13, color: 'var(--neutral-6)' }}>
            Edits below re-score the latest matrix run live — impact appears as you drag. Save bumps the rubric version and triggers a fresh matrix run.
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <Btn variant="ghost" icon={<IconRefresh size={13} />} onClick={reset} disabled={!isDirty}>Reset</Btn>
          <Btn variant="default" onClick={() => setShowSave(true)} disabled={!canSave}>
            Save rubric
          </Btn>
        </div>
      </div>

      {/* tier picker */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'nowrap' }}>
        {MMFP_TIERS.map(t => {
          const isActive = t.id === tierId;
          const tierDirty = JSON.stringify(edited[t.id]) !== JSON.stringify(MMFP_DIMENSIONS[t.id]);
          return (
            <button key={t.id} onClick={() => setTierId(t.id)} style={{
              flex: 1, minWidth: 0,
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 14px', borderRadius: 8, fontFamily: 'inherit', fontSize: 12,
              border: '1px solid ' + (isActive ? 'var(--neutral-1)' : 'var(--neutral-11)'),
              background: isActive ? '#fff' : 'var(--neutral-13)',
              cursor: 'pointer', textAlign: 'left',
              boxShadow: isActive ? 'var(--shadow-xs)' : 'none', whiteSpace: 'nowrap',
            }}>
              <span style={{ flexShrink: 0 }}><TierPill tier={t} colorOn={colorOn} /></span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontWeight: 600, color: 'var(--neutral-1)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.name}</div>
                <div style={{ fontSize: 11, color: 'var(--neutral-6)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {MMFP_DIMENSIONS[t.id].length} dims · {Object.keys(MMFP_RUNS[t.id]).length} cands
                </div>
              </div>
              {tierDirty && <span style={{ flexShrink: 0 }}><Chip tone="warn">edited</Chip></span>}
            </button>
          );
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <RubricCard title={`Current · ${rubricVersion}`} rubric={currentRubric} mode="view"
                    badge={<Chip tone="neutral">live · YAML</Chip>} onChange={() => {}} />
        <RubricCard title="Edited · live preview" rubric={editedRubric} mode="edit"
                    badge={isDirty
                      ? <Chip tone="warn">unsaved · {totalEd}%</Chip>
                      : <Chip tone="success">in sync</Chip>}
                    onChange={setEditedRubric} />
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase' }}>
            Live impact · re-scored {MMFP_LATEST_RUN.tasks.toLocaleString()} tasks from <span style={{ fontFamily: 'var(--font-mono)' }}>{MMFP_LATEST_RUN.id}</span>
          </div>
          <span style={{ fontSize: 11, color: isDirty ? 'var(--warm-red)' : 'var(--green)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            {isDirty
              ? <><IconAlert size={12} color="var(--warm-red)" /> editing · {totalEd === 100 ? 'ready to save' : `Σ must be 100% (currently ${totalEd}%)`}</>
              : <><IconCheck size={12} color="var(--green)" /> matches saved rubric</>}
          </span>
        </div>
        <LiveCompare tier={tier} currentRubric={currentRubric} editedRubric={editedRubric} colorOn={colorOn} />
      </div>

      <div style={{ marginTop: 18, fontSize: 11, color: 'var(--neutral-6)', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
        Re-scoring uses cached evaluator outputs in LangSmith — no inference cost.
        Rubric history is auditable in <a href="#">products/{product.id}/rubric-config.yaml</a>.
      </div>

      {/* Save modal */}
      <Modal open={showSave} onClose={() => !saving && setShowSave(false)} title={`Save rubric · ${tier.code}`} width={580}>
        <div style={{ fontSize: 13, color: 'var(--neutral-3)', marginBottom: 12 }}>
          This will commit the edited weights as a new rubric version, re-score the latest matrix run, and update the Scoreboard.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 14px', fontSize: 12, padding: 12, background: 'var(--neutral-13)', borderRadius: 8, marginBottom: 14 }}>
          <span style={{ color: 'var(--neutral-6)' }}>Product</span>
          <span style={{ fontWeight: 500 }}>{product.full}</span>
          <span style={{ color: 'var(--neutral-6)' }}>Tier</span>
          <span><TierPill tier={tier} colorOn={colorOn} /> {tier.name}</span>
          <span style={{ color: 'var(--neutral-6)' }}>Version</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>
            {rubricVersion} → <strong>{nextVersion(rubricVersion)}</strong>
          </span>
          <span style={{ color: 'var(--neutral-6)' }}>Author</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>wayne.palmer</span>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--neutral-3)', display: 'block', marginBottom: 6 }}>
            Why are you changing this? <span style={{ color: 'var(--neutral-6)', fontWeight: 400 }}>(stored on the version)</span>
          </label>
          <textarea value={note} onChange={e => setNote(e.target.value)}
            placeholder="e.g. Reweight citation faithfulness toward synthesis after Q4 review."
            style={{
              width: '100%', minHeight: 76, padding: 10,
              border: '1px solid var(--neutral-10)', borderRadius: 6,
              fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--neutral-1)',
              resize: 'vertical', boxSizing: 'border-box', outline: 'none',
            }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Btn variant="ghost" onClick={() => setShowSave(false)} disabled={saving}>Cancel</Btn>
          <Btn variant="default" onClick={commitSave} disabled={saving || !note.trim()}>
            {saving ? 'Saving…' : 'Save rubric'}
          </Btn>
        </div>
      </Modal>
    </div>
  );
}

window.Editor = Editor;
