/* global React, MMFP_TIERS, MMFP_CANDIDATES, MMFP_RUNS, MMFP_TREND_LABELS, MMFP_TRENDS,
   MMFP_DRIFT, MMFP_LATEST_RUN, Btn, Chip, Panel, SectionHeader, TierPill, TierRule,
   Delta, Spark, Modal,
   IconCheck, IconX, IconChevron, IconChevronR, IconAlert, IconInfo, IconDownload,
   IconLink, IconRefresh, IconTrend, IconExternal, IconLock, IconBeaker */
const { useState: useScoreState } = React;

function candById(id) { return MMFP_CANDIDATES.find(c => c.id === id); }

function FamilyDot({ family }) {
  const m = {
    frontier: { color: 'var(--blue-2)', label: 'Frontier' },
    'fine-tune': { color: 'var(--orange)', label: 'Fine-tune' },
    custom: { color: 'var(--purple)', label: 'Custom' },
  };
  const f = m[family] || m.frontier;
  return <span title={f.label} style={{
    display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
    background: f.color, flexShrink: 0,
  }} />;
}

function StatusPill({ status }) {
  const s = {
    primary:  { tone: 'primary', label: 'Approved · Primary' },
    fallback: { tone: 'success', label: 'Approved · Fallback' },
    eval:     { tone: 'info',    label: 'Under evaluation' },
    rejected: { tone: 'danger',  label: 'Rejected' },
  }[status] || { tone: 'neutral', label: status };
  return <Chip tone={s.tone}>{s.label}</Chip>;
}

function DriftBanner({ drift, showDrift }) {
  if (!showDrift || drift.length === 0) return null;
  return (
    <div style={{
      background: 'var(--light-yellow)', border: '1px solid #f0d690',
      borderRadius: 10, padding: '12px 16px',
      display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16,
    }}>
      <IconAlert size={18} color="#8a6600" />
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#5e4400' }}>
          {drift.length} active drift signal{drift.length > 1 ? 's' : ''} from production
        </div>
        <div style={{ fontSize: 12, color: '#8a6600', marginTop: 2 }}>
          Online evaluators are flagging divergence from latest evaluation scores. Review before next portfolio cycle.
        </div>
      </div>
      <Btn variant="outline" size="sm">View signals</Btn>
    </div>
  );
}

function TierCard({ tier, runs, trends, dimensions, drift, expanded, onToggle, density, colorOn, showDrift, onAction }) {
  const rows = Object.entries(runs).map(([cid, r]) => ({ cid, ...r, cand: candById(cid) }));
  const primary  = rows.find(r => r.role === 'primary');
  const fallback = rows.find(r => r.role === 'fallback');
  const evals    = rows.filter(r => r.status === 'eval');
  const rejected = rows.filter(r => r.status === 'rejected');
  const tierDrift = drift.filter(d => d.tier === tier.id);
  const padY = density === 'dense' ? 6 : 10;

  return (
    <Panel style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'stretch' }}>
        <TierRule tier={tier} colorOn={colorOn} w={4} />
        <div style={{ flex: 1, padding: '14px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <TierPill tier={tier} colorOn={colorOn} />
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--neutral-1)' }}>{tier.name}</div>
              <div style={{ fontSize: 12, color: 'var(--neutral-6)', marginTop: 2 }}>{tier.blurb}</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {showDrift && tierDrift.length > 0 && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#8a6600', fontWeight: 600 }}>
                <IconAlert size={14} color="#8a6600" />{tierDrift.length} drift
              </span>
            )}
            <span style={{ fontSize: 11, color: 'var(--neutral-6)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
              {rows.length} cands · {dimensions.length} dims
            </span>
            <button onClick={onToggle} style={{
              background: 'transparent', border: '1px solid var(--neutral-11)', borderRadius: 6,
              padding: '6px 10px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
              fontSize: 12, fontFamily: 'inherit', color: 'var(--neutral-3)', fontWeight: 500, whiteSpace: 'nowrap',
            }}>
              {expanded ? 'Collapse' : 'Open scorecard'}
              <span style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 150ms' }}>
                <IconChevronR size={12} />
              </span>
            </button>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr 1fr', gap: 0, borderTop: '1px solid var(--neutral-11)' }}>
        <PortfolioSlot label="Primary" runRow={primary} tierTrend={trends} colorOn={colorOn} accent={tier.accent} />
        <PortfolioSlot label="Fallback" runRow={fallback} tierTrend={trends} colorOn={colorOn} accent={tier.accent} sep />
        <div style={{ padding: '14px 18px', borderLeft: '1px solid var(--neutral-11)' }}>
          <div style={{ fontSize: 11, color: 'var(--neutral-6)', fontWeight: 600, letterSpacing: 0.4, textTransform: 'uppercase' }}>Under evaluation</div>
          <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--neutral-1)', marginTop: 6, letterSpacing: '-0.01em' }}>{evals.length}</div>
          <div style={{ fontSize: 12, color: 'var(--neutral-6)', marginTop: 2 }}>
            {evals.slice(0, 2).map(r => r.cand.name).join(', ')}{evals.length > 2 ? `, +${evals.length - 2}` : ''}
          </div>
        </div>
        <div style={{ padding: '14px 18px', borderLeft: '1px solid var(--neutral-11)' }}>
          <div style={{ fontSize: 11, color: 'var(--neutral-6)', fontWeight: 600, letterSpacing: 0.4, textTransform: 'uppercase' }}>Rejected</div>
          <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--neutral-4)', marginTop: 6, letterSpacing: '-0.01em' }}>{rejected.length}</div>
          <div style={{ fontSize: 12, color: 'var(--neutral-6)', marginTop: 2 }}>
            {rejected.length > 0 ? `Top: ${rejected[0].reason.split(' (')[0].toLowerCase()}` : '—'}
          </div>
        </div>
      </div>

      {expanded && (
        <Scorecard tier={tier} rows={rows} dimensions={dimensions}
                   trends={trends} drift={drift}
                   density={density} colorOn={colorOn} showDrift={showDrift}
                   padY={padY} onAction={onAction} />
      )}
    </Panel>
  );
}

function PortfolioSlot({ label, runRow, tierTrend, colorOn, accent, sep }) {
  if (!runRow) {
    return (
      <div style={{ padding: '14px 18px', borderLeft: sep ? '1px solid var(--neutral-11)' : 'none' }}>
        <div style={{ fontSize: 11, color: 'var(--neutral-6)', fontWeight: 600, letterSpacing: 0.4, textTransform: 'uppercase' }}>{label}</div>
        <div style={{ fontSize: 14, color: 'var(--neutral-7)', marginTop: 8 }}>— none —</div>
      </div>
    );
  }
  const trend = tierTrend[runRow.cid] || [];
  return (
    <div style={{ padding: '14px 18px', borderLeft: sep ? '1px solid var(--neutral-11)' : 'none' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 11, color: 'var(--neutral-6)', fontWeight: 600, letterSpacing: 0.4, textTransform: 'uppercase' }}>{label}</div>
        <FamilyDot family={runRow.cand.family} />
      </div>
      <div style={{ fontSize: 17, fontWeight: 600, color: 'var(--neutral-1)', marginTop: 6 }}>{runRow.cand.name}</div>
      <div style={{ fontSize: 12, color: 'var(--neutral-6)', marginTop: 1 }}>
        {runRow.cand.vendor} · {runRow.cand.binding}
        {runRow.cand.base ? ` · base: ${runRow.cand.base}` : ''}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 600,
          color: 'var(--neutral-1)', letterSpacing: '-0.02em',
        }}>{runRow.composite.toFixed(1)}</span>
        <Spark data={trend} stroke={colorOn ? accent : 'var(--neutral-4)'} w={70} h={24} />
        <Delta value={trend.length >= 2 ? trend[trend.length - 1] - trend[trend.length - 2] : 0} />
      </div>
    </div>
  );
}

function Scorecard({ tier, rows, dimensions, trends, drift, density, colorOn, showDrift, padY, onAction }) {
  const [openCid, setOpenCid] = useScoreState(null);
  const sorted = [...rows].sort((a, b) => b.composite - a.composite);
  const hasPrimary = rows.some(r => r.role === 'primary');
  const hasFallback = rows.some(r => r.role === 'fallback');

  return (
    <div style={{ borderTop: '1px solid var(--neutral-11)', background: 'var(--neutral-13)' }}>
      <div style={{ padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase' }}>
          Latest matrix run · scorecard
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 11, color: 'var(--neutral-6)' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><FamilyDot family="frontier" /> Frontier</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><FamilyDot family="fine-tune" /> Fine-tune</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><FamilyDot family="custom" /> Custom</span>
        </div>
      </div>
      <div style={{ padding: '0 18px 16px' }}>
        <div style={{ background: '#fff', border: '1px solid var(--neutral-11)', borderRadius: 8, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontFamily: 'var(--font-sans)' }}>
            <thead>
              <tr style={{ background: 'var(--neutral-13)', borderBottom: '1px solid var(--neutral-11)' }}>
                <th style={th()}>#</th>
                <th style={{ ...th(), textAlign: 'left' }}>Candidate</th>
                <th style={th()}>Status</th>
                <th style={{ ...th(), textAlign: 'right' }}>Composite</th>
                {dimensions.map(d => (
                  <th key={d.id} style={{ ...th(), textAlign: 'right' }} title={d.desc}>
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      {d.label}{d.gate && <IconLock size={10} color="var(--neutral-6)" />}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--neutral-7)', fontFamily: 'var(--font-mono)', fontWeight: 400, marginTop: 2 }}>{d.weight}%</div>
                  </th>
                ))}
                <th style={th()}>Trend</th>
                <th style={th()}></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => {
                const trend = trends[r.cid] || [];
                const isOpen = openCid === r.cid;
                const candDrift = drift.find(d => d.candidate === r.cid && d.tier === tier.id);
                return (
                  <React.Fragment key={r.cid}>
                    <tr style={{ borderBottom: '1px solid var(--neutral-12)' }}>
                      <td style={td(padY)}>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--neutral-6)' }}>{i + 1}</span>
                      </td>
                      <td style={td(padY)}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <FamilyDot family={r.cand.family} />
                          <span style={{ fontWeight: 500, color: 'var(--neutral-1)' }}>{r.cand.name}</span>
                          <span style={{ fontSize: 11, color: 'var(--neutral-6)' }}>· {r.cand.vendor}</span>
                        </div>
                        {r.status === 'rejected' && (
                          <div style={{ fontSize: 11, color: 'var(--warm-red)', marginTop: 2 }}>{r.reason}</div>
                        )}
                      </td>
                      <td style={td(padY)}><StatusPill status={r.status === 'approved' ? r.role : r.status} /></td>
                      <td style={{ ...td(padY), textAlign: 'right' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 13, color: 'var(--neutral-1)' }}>
                          {r.composite.toFixed(1)}
                        </span>
                      </td>
                      {dimensions.map(d => {
                        const v = r.dims[d.id];
                        const gateFail = d.gate && r.status === 'rejected' && r.reason.toLowerCase().includes(d.label.toLowerCase().split(' ')[0]);
                        return (
                          <td key={d.id} style={{ ...td(padY), textAlign: 'right', fontFamily: 'var(--font-mono)',
                                                  color: gateFail ? 'var(--warm-red)' : 'var(--neutral-2)',
                                                  fontWeight: gateFail ? 600 : 400 }}>
                            {formatDim(v, d)}
                          </td>
                        );
                      })}
                      <td style={td(padY)}>
                        <Spark data={trend} stroke={colorOn ? tier.accent : 'var(--neutral-4)'} w={60} h={20} />
                      </td>
                      <td style={td(padY)}>
                        {showDrift && candDrift && (
                          <span title={candDrift.summary} style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            background: 'var(--light-yellow)', color: '#8a6600',
                            padding: '2px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                          }}>
                            <IconAlert size={10} color="#8a6600" />drift
                          </span>
                        )}
                        <button onClick={() => setOpenCid(isOpen ? null : r.cid)} style={{
                          marginLeft: 6, background: 'transparent', border: 'none', cursor: 'pointer',
                          color: 'var(--neutral-6)', padding: 4,
                          transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform 150ms',
                        }}>
                          <IconChevronR size={14} />
                        </button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={dimensions.length + 6} style={{ padding: 0, background: 'var(--neutral-13)' }}>
                          <CandidateDetail row={r} dimensions={dimensions} drift={candDrift} trend={trend}
                            colorOn={colorOn} accent={tier.accent} tier={tier}
                            hasPrimary={hasPrimary} hasFallback={hasFallback}
                            onAction={onAction} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function th() { return { padding: '8px 10px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: 'var(--neutral-5)', borderRight: '1px solid var(--neutral-12)' }; }
function td(padY) { return { padding: `${padY}px 10px`, fontSize: 12, color: 'var(--neutral-2)', borderRight: '1px solid var(--neutral-12)', verticalAlign: 'middle' }; }
function formatDim(v, d) {
  if (v == null) return '—';
  if (d.unit === 'ms') return v >= 1000 ? (v / 1000).toFixed(2) + 's' : Math.round(v) + 'ms';
  if (d.unit === '%')  return v.toFixed(1) + '%';
  if (d.unit === 'F1') return v.toFixed(2);
  if (d.unit === '/5') return v.toFixed(1);
  if (d.unit === 's')  return v.toFixed(1) + 's';
  if (d.unit === '¢')  return '$' + (v / 100).toFixed(3);
  return v;
}

function CandidateDetail({ row, dimensions, drift, trend, colorOn, accent, tier, hasPrimary, hasFallback, onAction }) {
  return (
    <div style={{ padding: 18, borderTop: '1px solid var(--neutral-11)', display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: 18 }}>
      <div>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 8 }}>
          Per-dimension breakdown
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {dimensions.map(d => {
            const v = row.dims[d.id];
            const norm = Math.min(100, Math.max(0, normalize(v, d)));
            return (
              <div key={d.id} style={{ display: 'grid', gridTemplateColumns: '1.4fr 0.6fr 1.6fr', gap: 10, alignItems: 'center', fontSize: 12 }}>
                <span style={{ color: 'var(--neutral-3)' }}>
                  {d.label}{d.gate && <IconLock size={10} color="var(--neutral-6)" style={{ marginLeft: 4, verticalAlign: 'middle' }} />}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', textAlign: 'right', fontWeight: 600, color: 'var(--neutral-1)' }}>
                  {formatDim(v, d)}
                </span>
                <div style={{ height: 6, background: 'var(--neutral-12)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ width: norm + '%', height: '100%', background: colorOn ? accent : 'var(--neutral-4)' }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 8 }}>
          Composite score · 6 quarters
        </div>
        <Panel padding={12}>
          <Spark data={trend} stroke={colorOn ? accent : 'var(--neutral-4)'} w={260} h={70} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--neutral-6)', fontFamily: 'var(--font-mono)', marginTop: 4 }}>
            {MMFP_TREND_LABELS.map(l => <span key={l}>{l}</span>)}
          </div>
        </Panel>
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--neutral-6)' }}>
          Binding: <span style={{ fontFamily: 'var(--font-mono)' }}>{row.cand.binding.toLowerCase()}</span> · Family: {row.cand.family}
          {row.cand.base ? ` · Base: ${row.cand.base}` : ''}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 8 }}>
          Decisions
        </div>
        <Panel padding={12}>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px 10px', fontSize: 12, marginBottom: 12 }}>
            <span style={{ color: 'var(--neutral-6)' }}>Run</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{MMFP_LATEST_RUN.id}</span>
            <span style={{ color: 'var(--neutral-6)' }}>Rubric</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{MMFP_LATEST_RUN.rubricVersion}</span>
            <span style={{ color: 'var(--neutral-6)' }}>LangSmith</span>
            <a href="#" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              experiment <IconExternal size={10} />
            </a>
          </div>
          {drift && (
            <div style={{ marginBottom: 12, padding: 10, background: 'var(--light-yellow)', borderRadius: 6, fontSize: 11, color: '#5e4400' }}>
              <strong>Drift signal:</strong> {drift.summary}
              <div style={{ marginTop: 4, color: '#8a6600' }}>Detected {drift.detected}</div>
            </div>
          )}
          {/* Decision actions */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {row.role !== 'primary' && row.gates !== false && row.status !== 'rejected' && (
              <Btn variant="default" size="sm"
                onClick={() => onAction({ kind: 'promote', candidate: row.cid, tier, toRole: 'primary' })}
                disabled={row.status === 'rejected'}>
                Promote to Primary
              </Btn>
            )}
            {row.role !== 'fallback' && row.status !== 'rejected' && (
              <Btn variant="outline" size="sm"
                onClick={() => onAction({ kind: 'promote', candidate: row.cid, tier, toRole: 'fallback' })}>
                Set as Fallback
              </Btn>
            )}
            {row.status !== 'rejected' && (
              <Btn variant="ghost" size="sm"
                onClick={() => onAction({ kind: 'reject', candidate: row.cid, tier })}
                style={{ color: 'var(--warm-red)' }}>
                Reject
              </Btn>
            )}
            {row.status === 'rejected' && (
              <Btn variant="outline" size="sm"
                onClick={() => onAction({ kind: 'reinstate', candidate: row.cid, tier })}>
                Move to Under evaluation
              </Btn>
            )}
          </div>
          <div style={{ marginTop: 8, fontSize: 10, color: 'var(--neutral-6)', fontStyle: 'italic' }}>
            Decisions write a portfolio entry to <span style={{ fontFamily: 'var(--font-mono)' }}>portfolio.yaml</span> with rationale and run reference.
          </div>
        </Panel>
      </div>
    </div>
  );
}

function normalize(v, d) {
  if (v == null) return 0;
  if (d.unit === '%' || d.unit === 'F1') return d.unit === 'F1' ? v * 100 : v;
  if (d.unit === '/5') return (v / 5) * 100;
  if (d.unit === 'ms') return Math.max(0, 100 - (v / 20));
  if (d.unit === 's')  return Math.max(0, 100 - v * 8);
  if (d.unit === '¢')  return Math.max(0, 100 - v * 8);
  return v;
}

// — Decision modal: promote / reject / reinstate with rationale —
function DecisionModal({ action, onClose, onConfirm }) {
  const [rationale, setRationale] = useScoreState('');
  React.useEffect(() => { setRationale(''); }, [action?.candidate, action?.kind]);
  if (!action) return null;
  const cand = candById(action.candidate);
  const titles = {
    promote: action.toRole === 'primary'
      ? `Promote ${cand.name} to Primary`
      : `Set ${cand.name} as Fallback`,
    reject: `Reject ${cand.name}`,
    reinstate: `Reinstate ${cand.name}`,
  };
  const placeholders = {
    promote: 'e.g. Sustained 92.1 composite over 3 quarters; ARB consensus; gate clean.',
    reject:  'e.g. Hallucination rate 3.4% — exceeds T3 gate of <2%. Recheck after vendor v3.',
    reinstate: 'e.g. Vendor v3.1 patch resolved gate fail in re-run.',
  };
  const ctas = { promote: 'Confirm decision', reject: 'Reject candidate', reinstate: 'Reinstate' };
  return (
    <Modal open onClose={onClose} title={titles[action.kind]} width={580}>
      <div style={{ fontSize: 13, color: 'var(--neutral-3)', marginBottom: 12 }}>
        {action.kind === 'promote' && action.toRole === 'primary' &&
          'This becomes the production primary for this tier. The previous primary moves to fallback automatically.'}
        {action.kind === 'promote' && action.toRole === 'fallback' &&
          'This becomes the production fallback for this tier.'}
        {action.kind === 'reject' && 'The candidate moves to Rejected and is excluded from portfolio consideration until reinstated.'}
        {action.kind === 'reinstate' && 'The candidate returns to Under evaluation and will appear in the next matrix run.'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 14px', fontSize: 12, padding: 12, background: 'var(--neutral-13)', borderRadius: 8, marginBottom: 14 }}>
        <span style={{ color: 'var(--neutral-6)' }}>Tier</span>
        <span><strong>{action.tier.code}</strong> · {action.tier.name}</span>
        <span style={{ color: 'var(--neutral-6)' }}>Candidate</span>
        <span style={{ fontWeight: 500 }}>{cand.name} · {cand.vendor}</span>
        <span style={{ color: 'var(--neutral-6)' }}>Run</span>
        <span style={{ fontFamily: 'var(--font-mono)' }}>{MMFP_LATEST_RUN.id}</span>
      </div>
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--neutral-3)', display: 'block', marginBottom: 6 }}>
          Rationale <span style={{ color: 'var(--neutral-6)', fontWeight: 400 }}>(stored on the decision; required)</span>
        </label>
        <textarea value={rationale} onChange={e => setRationale(e.target.value)}
          placeholder={placeholders[action.kind]}
          style={{
            width: '100%', minHeight: 76, padding: 10,
            border: '1px solid var(--neutral-10)', borderRadius: 6,
            fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--neutral-1)',
            resize: 'vertical', boxSizing: 'border-box', outline: 'none',
          }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn variant={action.kind === 'reject' ? 'destructive' : 'default'}
             onClick={() => onConfirm({ ...action, rationale })}
             disabled={!rationale.trim()}>
          {ctas[action.kind]}
        </Btn>
      </div>
    </Modal>
  );
}

// — Top-level scoreboard page —
function Scoreboard({ tweaks, onPdf, product, rubricVersion, onDecision }) {
  const [expanded, setExpanded] = useScoreState({ t1: false, t2: true, t3: false });
  const [filterTier, setFilterTier] = useScoreState('all');
  const [pendingAction, setPendingAction] = useScoreState(null);
  const colorOn = tweaks.colorOn;
  const showDrift = tweaks.showDrift;
  const density = tweaks.density;

  const tiers = filterTier === 'all' ? MMFP_TIERS : MMFP_TIERS.filter(t => t.id === filterTier);

  return (
    <div style={{ padding: 24, maxWidth: 1480, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 18, flexWrap: 'wrap', gap: 16 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--neutral-6)', letterSpacing: 0.4, textTransform: 'uppercase' }}>
            Portfolio · {product.name} · Production
          </div>
          <h1 style={{ margin: '6px 0 4px', fontSize: 26, letterSpacing: '-0.01em' }}>Approved model portfolio</h1>
          <div style={{ fontSize: 13, color: 'var(--neutral-6)' }}>
            Latest matrix run <span style={{ fontFamily: 'var(--font-mono)' }}>{MMFP_LATEST_RUN.id}</span> · scored under
            rubric <span style={{ fontFamily: 'var(--font-mono)' }}>{rubricVersion}</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <div style={{ display: 'inline-flex', background: '#fff', border: '1px solid var(--neutral-11)', borderRadius: 6, padding: 2 }}>
            {[{ id: 'all', l: 'All tiers' }, ...MMFP_TIERS.map(t => ({ id: t.id, l: t.code }))].map(o => (
              <button key={o.id} onClick={() => setFilterTier(o.id)} style={{
                padding: '5px 10px', fontSize: 12, border: 'none',
                background: filterTier === o.id ? 'var(--neutral-1)' : 'transparent',
                color: filterTier === o.id ? '#fff' : 'var(--neutral-3)',
                borderRadius: 4, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500,
              }}>{o.l}</button>
            ))}
          </div>
          <Btn variant="outline" icon={<IconLink size={13} />}>Stable URL</Btn>
          <Btn variant="default" icon={<IconDownload size={13} />} onClick={onPdf}>Export PDF</Btn>
        </div>
      </div>

      <DriftBanner drift={MMFP_DRIFT} showDrift={showDrift} />

      <Panel style={{ marginBottom: 16, padding: 0 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)' }}>
          <RunStat label="Tasks" value={MMFP_LATEST_RUN.tasks.toLocaleString()} />
          <RunStat label="Judge calls" value={MMFP_LATEST_RUN.judgeCallsK.toFixed(1) + 'k'} />
          <RunStat label="Run cost" value={'$' + MMFP_LATEST_RUN.costUsd.toFixed(2)} />
          <RunStat label="Duration" value={MMFP_LATEST_RUN.durationMin + 'm'} />
          <RunStat label="Started" value={'Apr 28 · 08:14'} />
          <RunStat label="Triggered" value="ci-runner" mono />
        </div>
      </Panel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {tiers.map(tier => (
          <TierCard key={tier.id} tier={tier}
                    runs={MMFP_RUNS[tier.id]}
                    trends={MMFP_TRENDS[tier.id]}
                    dimensions={MMFP_DIMENSIONS[tier.id]}
                    drift={MMFP_DRIFT}
                    expanded={expanded[tier.id]}
                    onToggle={() => setExpanded(e => ({ ...e, [tier.id]: !e[tier.id] }))}
                    density={density} colorOn={colorOn} showDrift={showDrift}
                    onAction={setPendingAction} />
        ))}
      </div>

      <div style={{ marginTop: 18, fontSize: 11, color: 'var(--neutral-6)', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
        Authority: <a href="#">products/{product.id}/rubric-config.yaml</a> · <a href="#">ADRs/0014-{product.id}-r1-portfolio.md</a> ·
        Decisions are version-controlled.
      </div>

      <DecisionModal action={pendingAction} onClose={() => setPendingAction(null)}
        onConfirm={(a) => { onDecision(a); setPendingAction(null); }} />
    </div>
  );
}

function RunStat({ label, value, mono }) {
  return (
    <div style={{ padding: '12px 16px', borderRight: '1px solid var(--neutral-11)' }}>
      <div style={{ fontSize: 11, color: 'var(--neutral-6)', fontWeight: 600, letterSpacing: 0.4, textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--neutral-1)', marginTop: 4, fontFamily: mono ? 'var(--font-mono)' : 'inherit' }}>{value}</div>
    </div>
  );
}

window.Scoreboard = Scoreboard;
