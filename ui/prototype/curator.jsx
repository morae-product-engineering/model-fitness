/* global React, MMFP_TIERS, MMFP_DATASETS, MMFP_JUDGE_QUEUE, MMFP_CANDIDATES,
   Btn, Chip, Panel, SectionHeader, TierPill, Modal,
   IconCheck, IconX, IconChevronR, IconAlert, IconInfo, IconPlus, IconSearch, IconFilter, IconExternal */
const { useState: useCurState, useMemo: useCurMemo } = React;

function tierById(id) { return MMFP_TIERS.find(t => t.id === id); }
function candByIdCur(id) { return MMFP_CANDIDATES.find(c => c.id === id); }

function CoverageBar({ value, accent }) {
  const pct = Math.round(value * 100);
  const tone = value > 0.8 ? 'var(--green)' : value > 0.65 ? 'var(--warm-yellow)' : 'var(--warm-red)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ flex: 1, height: 5, background: 'var(--neutral-12)', borderRadius: 3, overflow: 'hidden', minWidth: 80 }}>
        <div style={{ width: pct + '%', height: '100%', background: accent || tone }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: 'var(--neutral-2)', minWidth: 32 }}>{pct}%</span>
    </div>
  );
}

function DatasetTable({ datasets, colorOn, onAdd }) {
  return (
    <Panel padding={0}>
      <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--neutral-11)' }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>Golden datasets · MLI</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, height: 30,
            padding: '0 10px', border: '1px solid var(--neutral-11)', borderRadius: 6,
            background: '#fff',
          }}>
            <IconSearch size={13} color="var(--neutral-6)" />
            <input placeholder="Filter datasets…" style={{
              border: 'none', outline: 'none', fontSize: 12, fontFamily: 'inherit',
              width: 160, color: 'var(--neutral-1)',
            }} />
          </div>
          <Btn variant="outline" size="sm" icon={<IconFilter size={12} />}>Tier · all</Btn>
          <Btn variant="default" size="sm" icon={<IconPlus size={12} />} onClick={onAdd}>Add example</Btn>
        </div>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: 'var(--neutral-13)', borderBottom: '1px solid var(--neutral-11)' }}>
            <th style={cth()}>Tier</th>
            <th style={{ ...cth(), textAlign: 'left' }}>Name</th>
            <th style={cth()}>Version</th>
            <th style={{ ...cth(), textAlign: 'right' }}>Examples</th>
            <th style={{ ...cth(), textAlign: 'left' }}>Coverage</th>
            <th style={cth()}>Owner</th>
            <th style={cth()}>Last edit</th>
            <th style={cth()}></th>
          </tr>
        </thead>
        <tbody>
          {datasets.map(d => {
            const t = d.tier !== '—' ? tierById(d.tier) : null;
            return (
              <tr key={d.id} style={{ borderBottom: '1px solid var(--neutral-12)' }}>
                <td style={ctd()}>
                  {t ? <TierPill tier={t} colorOn={colorOn} /> : <Chip tone="neutral">shared</Chip>}
                </td>
                <td style={ctd()}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'var(--neutral-1)' }}>{d.name}</div>
                </td>
                <td style={{ ...ctd(), fontFamily: 'var(--font-mono)', color: 'var(--neutral-6)' }}>{d.version}</td>
                <td style={{ ...ctd(), textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{d.count}</td>
                <td style={{ ...ctd(), minWidth: 160 }}>
                  <CoverageBar value={d.coverage} accent={colorOn && t ? t.accent : null} />
                </td>
                <td style={{ ...ctd(), color: 'var(--neutral-3)' }}>{d.owner}</td>
                <td style={{ ...ctd(), color: 'var(--neutral-6)', fontFamily: 'var(--font-mono)' }}>{d.lastEdit}</td>
                <td style={ctd()}>
                  <button style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--neutral-6)' }}>
                    <IconChevronR size={14} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}

function cth() { return { padding: '8px 12px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: 'var(--neutral-5)', whiteSpace: 'nowrap' }; }
function ctd() { return { padding: '10px 12px', verticalAlign: 'middle', textAlign: 'center' }; }

function JudgeRow({ row, onMark, expanded, onToggle, colorOn }) {
  const t = tierById(row.tier);
  const cand = candByIdCur(row.candidate);
  const tones = {
    pending:  { tone: 'neutral', label: 'Pending review' },
    agree:    { tone: 'success', label: 'Agreed' },
    disagree: { tone: 'danger',  label: 'Disagreed' },
  };
  return (
    <div style={{ borderBottom: '1px solid var(--neutral-12)' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '60px 1.2fr 1fr 90px 80px 200px 120px', gap: 12, alignItems: 'center', padding: '12px 16px' }}>
        <TierPill tier={t} colorOn={colorOn} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 12, color: 'var(--neutral-1)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {row.task}
          </div>
          <div style={{ fontSize: 11, color: 'var(--neutral-6)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
            {row.dataset}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 12, color: 'var(--neutral-1)', fontWeight: 500 }}>{cand.name}</div>
          <div style={{ fontSize: 11, color: 'var(--neutral-6)' }}>scored on <span style={{ fontFamily: 'var(--font-mono)' }}>{row.dim}</span></div>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--neutral-1)', textAlign: 'right' }}>
          {typeof row.judgeScore === 'number' ? (row.judgeScore < 5 ? row.judgeScore.toFixed(1) : row.judgeScore + (row.judgeScore <= 1 ? '' : '%')) : row.judgeScore}
        </div>
        <div><Chip tone={tones[row.status].tone}>{tones[row.status].label}</Chip></div>
        <div style={{ display: 'flex', gap: 4 }}>
          <Btn variant={row.status === 'agree' ? 'default' : 'outline'} size="sm" icon={<IconCheck size={11} />}
               onClick={() => onMark(row.id, 'agree')}>Agree</Btn>
          <Btn variant={row.status === 'disagree' ? 'destructive' : 'outline'} size="sm" icon={<IconX size={11} />}
               onClick={() => onMark(row.id, 'disagree')}>Dispute</Btn>
        </div>
        <button onClick={onToggle} style={{
          background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--neutral-6)',
          display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, fontFamily: 'inherit',
        }}>
          {expanded ? 'Hide' : 'Trace'}
          <span style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 150ms' }}>
            <IconChevronR size={12} />
          </span>
        </button>
      </div>
      {expanded && (
        <div style={{ padding: '0 16px 14px 76px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <Panel padding={12} style={{ background: 'var(--neutral-13)' }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 6 }}>Judge reasoning</div>
            <div style={{ fontSize: 12, color: 'var(--neutral-2)', lineHeight: 1.5 }}>{row.judgeReason}</div>
            {row.note && (
              <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--neutral-11)' }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--warm-red)', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 4 }}>Curator note</div>
                <div style={{ fontSize: 12, color: 'var(--neutral-2)' }}>{row.note}</div>
              </div>
            )}
          </Panel>
          <Panel padding={12} style={{ background: 'var(--neutral-13)' }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 6 }}>Lineage</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 10px', fontSize: 11 }}>
              <span style={{ color: 'var(--neutral-6)' }}>Trace</span>
              <a href="#" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontFamily: 'var(--font-mono)' }}>
                ls/trc/{row.id} <IconExternal size={10} />
              </a>
              <span style={{ color: 'var(--neutral-6)' }}>Run</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>run-2026-04-28-mli-r1</span>
              <span style={{ color: 'var(--neutral-6)' }}>Judge</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>judge:claude-opus-4-1@v3</span>
              <span style={{ color: 'var(--neutral-6)' }}>Sensitivity</span>
              <span><Chip tone="ai">client-classified · ZDR</Chip></span>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}

function Curator({ tweaks, setToast }) {
  const colorOn = tweaks.colorOn;
  const [queue, setQueue] = useCurState(MMFP_JUDGE_QUEUE);
  const [openId, setOpenId] = useCurState(null);
  const [showAdd, setShowAdd] = useCurState(false);
  const [activeTab, setActiveTab] = useCurState('datasets');

  const counts = useCurMemo(() => ({
    pending: queue.filter(q => q.status === 'pending').length,
    agree: queue.filter(q => q.status === 'agree').length,
    disagree: queue.filter(q => q.status === 'disagree').length,
  }), [queue]);

  function mark(id, status) {
    setQueue(q => q.map(r => r.id === id ? { ...r, status, note: status === 'disagree' && !r.note ? '(curator note required on commit)' : r.note } : r));
    setToast(`Marked ${status} · queued for next steward review`);
  }

  return (
    <div style={{ padding: 24, maxWidth: 1480, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase' }}>
            Curator · golden datasets & judge calibration
          </div>
          <h1 style={{ margin: '6px 0 4px', fontSize: 26, letterSpacing: '-0.01em' }}>Dataset stewardship</h1>
          <div style={{ fontSize: 13, color: 'var(--neutral-6)' }}>
            Add new examples, review LLM-judge sample queue, flag disputed scores. Disputes feed the next rubric revisit.
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 11, color: '#8a6600', background: 'var(--light-yellow)',
            padding: '4px 10px', borderRadius: 4, fontWeight: 600,
            display: 'inline-flex', alignItems: 'center', gap: 6,
          }}>
            <IconInfo size={12} color="#8a6600" />
            v0.2 · curator flow shipping behind feature flag
          </span>
        </div>
      </div>

      {/* sub tabs */}
      <div style={{ display: 'flex', gap: 6, borderBottom: '1px solid var(--neutral-11)', marginBottom: 14 }}>
        {[
          { id: 'datasets',  l: 'Golden datasets', sub: `${MMFP_DATASETS.length} datasets` },
          { id: 'queue',     l: 'Judge sample queue', sub: `${counts.pending} pending` },
          { id: 'coverage',  l: 'Coverage by tag', sub: 'tagged taxonomy' },
        ].map(t => {
          const active = activeTab === t.id;
          return (
            <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
              position: 'relative', padding: '10px 14px', background: 'transparent', border: 'none',
              cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: active ? 600 : 500,
              color: active ? 'var(--neutral-1)' : 'var(--neutral-6)',
              display: 'inline-flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap',
            }}>
              <span>{t.l}</span>
              <span style={{ fontSize: 11, color: 'var(--neutral-6)', fontWeight: 400, whiteSpace: 'nowrap' }}>{t.sub}</span>
              {active && <span style={{ position: 'absolute', left: 14, right: 14, bottom: -1, height: 2, background: 'var(--neutral-1)' }} />}
            </button>
          );
        })}
      </div>

      {activeTab === 'datasets' && (
        <DatasetTable datasets={MMFP_DATASETS} colorOn={colorOn} onAdd={() => setShowAdd(true)} />
      )}

      {activeTab === 'queue' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0, background: '#fff', border: '1px solid var(--neutral-11)', borderRadius: 10, overflow: 'hidden' }}>
            <QueueStat label="In queue" value={queue.length} sub="this cycle" />
            <QueueStat label="Pending" value={counts.pending} tone="warn" sub="awaiting review" />
            <QueueStat label="Agreed" value={counts.agree} tone="good" sub="judge confirmed" />
            <QueueStat label="Disputed" value={counts.disagree} tone="danger" sub="goes to stewards" />
          </div>
          <Panel padding={0}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--neutral-11)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase' }}>
                LLM-judge sample queue · 2.5% of judged tasks sampled
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Btn variant="outline" size="sm">Filter</Btn>
                <Btn variant="ghost" size="sm" icon={<IconExternal size={12} />}>Open in LangSmith</Btn>
              </div>
            </div>
            {queue.map(r => (
              <JudgeRow key={r.id} row={r} colorOn={colorOn}
                        expanded={openId === r.id}
                        onToggle={() => setOpenId(openId === r.id ? null : r.id)}
                        onMark={mark} />
            ))}
          </Panel>
        </div>
      )}

      {activeTab === 'coverage' && (
        <Panel padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 14 }}>
            Coverage by intent × complexity · MLI golden sets
          </div>
          <CoverageGrid colorOn={colorOn} />
        </Panel>
      )}

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add golden example" width={620}>
        <div style={{ fontSize: 13, color: 'var(--neutral-6)', marginBottom: 14 }}>
          Schema-validated. Runs the schema-only evaluator dry-run before staging.
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <CField label="Target dataset">
            <select style={selStyle()}>
              <option>mli/extraction-golden v1.8.0</option>
              <option>mli/synthesis-golden v1.2.0</option>
              <option>mli/citation-faithfulness v0.9.1</option>
            </select>
          </CField>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <CField label="Intent tag">
              <select style={selStyle()}>
                <option>extract.parties</option>
                <option>extract.governing-law</option>
                <option>extract.effective-date</option>
              </select>
            </CField>
            <CField label="Complexity">
              <select style={selStyle()}>
                <option>1 — single clause</option>
                <option>2 — multi-clause</option>
                <option>3 — cross-document</option>
              </select>
            </CField>
          </div>
          <CField label="Task prompt">
            <textarea rows={3} placeholder="Extract all parties, governing law, and effective date…" style={{ ...selStyle(), height: 'auto', padding: 10, resize: 'vertical' }} />
          </CField>
          <CField label="Golden answer (JSON)">
            <textarea rows={4} placeholder='{ "parties": [...], "governing_law": "...", "effective_date": "..." }' style={{ ...selStyle(), height: 'auto', padding: 10, resize: 'vertical', fontFamily: 'var(--font-mono)', fontSize: 12 }} />
          </CField>
          <CField label="Sensitivity">
            <div style={{ display: 'flex', gap: 8 }}>
              <Chip tone="success">internal</Chip>
              <Chip tone="info">redacted</Chip>
              <Chip tone="ai">client-classified</Chip>
            </div>
          </CField>
        </div>
        <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--neutral-6)' }}>
            Submission opens a PR against <span style={{ fontFamily: 'var(--font-mono)' }}>products/mli/datasets/</span>
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn variant="ghost" onClick={() => setShowAdd(false)}>Cancel</Btn>
            <Btn variant="default" onClick={() => { setShowAdd(false); setToast('Schema validated · staged for PR review'); }}>Validate & stage</Btn>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function CField({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-3)', letterSpacing: 0.2 }}>{label}</label>
      {children}
    </div>
  );
}
function selStyle() {
  return {
    height: 36, padding: '0 10px', fontSize: 13, border: '1px solid var(--neutral-10)',
    borderRadius: 4, background: '#fff', fontFamily: 'inherit', color: 'var(--neutral-1)',
    width: '100%', boxSizing: 'border-box', outline: 'none',
  };
}

function QueueStat({ label, value, sub, tone = 'neutral' }) {
  const c = { neutral: 'var(--neutral-1)', good: 'var(--green)', warn: '#8a6600', danger: 'var(--warm-red)' }[tone];
  return (
    <div style={{ padding: '12px 16px', borderRight: '1px solid var(--neutral-11)' }}>
      <div style={{ fontSize: 11, color: 'var(--neutral-6)', fontWeight: 600, letterSpacing: 0.4, textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 600, color: c, marginTop: 4, letterSpacing: '-0.01em' }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--neutral-6)', marginTop: 2 }}>{sub}</div>
    </div>
  );
}

function CoverageGrid({ colorOn }) {
  const intents = ['route.intent', 'extract.parties', 'extract.terms', 'extract.dates', 'tool.lookup', 'synth.summary', 'synth.compare', 'cite.clause'];
  const complexities = ['1 · simple', '2 · multi-clause', '3 · cross-doc'];
  function cellPct(intent, cx) {
    // deterministic pseudo-random
    const h = (intent + cx).split('').reduce((s, ch) => s + ch.charCodeAt(0), 0);
    return ((h * 7) % 100);
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', fontSize: 11, fontFamily: 'var(--font-sans)' }}>
        <thead>
          <tr>
            <th style={{ padding: '6px 10px', textAlign: 'left', color: 'var(--neutral-6)' }} />
            {complexities.map(c => <th key={c} style={{ padding: '6px 10px', fontWeight: 600, color: 'var(--neutral-3)', textAlign: 'left' }}>{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {intents.map(i => (
            <tr key={i}>
              <td style={{ padding: '4px 10px', fontWeight: 500, color: 'var(--neutral-1)', fontFamily: 'var(--font-mono)' }}>{i}</td>
              {complexities.map(c => {
                const v = cellPct(i, c);
                const t = v > 70 ? 'var(--green)' : v > 40 ? 'var(--warm-yellow)' : 'var(--warm-red)';
                return (
                  <td key={c} style={{ padding: 4 }}>
                    <div style={{
                      width: 110, height: 32, borderRadius: 4,
                      background: `linear-gradient(90deg, ${t} ${v}%, var(--neutral-12) ${v}%)`,
                      display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                      padding: '0 8px', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
                      color: 'var(--neutral-1)',
                    }}>{v}%</div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

window.Curator = Curator;
