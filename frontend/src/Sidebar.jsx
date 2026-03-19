const EXAMPLES = [
  { label: 'List materials', query: 'What materials are available in the database?' },
  { label: 'Summarise property', query: 'Summarise all tensile strength data for Fancyplast 42' },
  { label: 'Trend analysis', query: 'Is there a decreasing trend in tensile strength for Fancyplast 42 over the last 6 months?' },
  { label: 'Machine comparison', query: 'How do Machine A and Machine B differ for tensile strength of Fancyplast 42? Are the differences statistically significant?' },
  { label: 'Correlation check', query: 'Does temperature correlate with elongation for Fancyplast 42?' },
  { label: 'Boundary risk', query: 'Is there an indication that tensile strength for Fancyplast 42 will violate the lower boundary of 45 MPa in the future?' },
]

const s = {
  sidebar: {
    background: 'var(--bg2)',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  logo: {
    padding: '20px 16px 14px',
    borderBottom: '1px solid var(--border)',
  },
  logoMark: {
    fontFamily: 'var(--font-mono)',
    fontWeight: 500,
    fontSize: '15px',
    color: 'var(--accent)',
    letterSpacing: '0.05em',
  },
  logoSub: {
    fontSize: '11px',
    color: 'var(--text3)',
    marginTop: '2px',
    fontFamily: 'var(--font-mono)',
  },
  section: {
    padding: '14px 16px 6px',
    fontSize: '10px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text3)',
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  examples: {
    flex: 1,
    overflowY: 'auto',
    padding: '4px 8px',
  },
  exBtn: {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    background: 'none',
    border: 'none',
    borderRadius: 'var(--radius)',
    padding: '8px 10px',
    cursor: 'pointer',
    color: 'var(--text2)',
    fontSize: '12px',
    fontFamily: 'var(--font-sans)',
    lineHeight: 1.4,
    transition: 'background 0.15s, color 0.15s',
    marginBottom: '2px',
  },
  footer: {
    padding: '12px 16px',
    borderTop: '1px solid var(--border)',
    fontSize: '11px',
    color: 'var(--text3)',
    fontFamily: 'var(--font-mono)',
  },
}

export default function Sidebar({ onSelectExample }) {
  return (
    <aside style={s.sidebar}>
      <div style={s.logo}>
        <div style={s.logoMark}>MAT//AI</div>
        <div style={s.logoSub}>material testing assistant</div>
      </div>

      <div style={s.section}>example queries</div>
      <div style={s.examples}>
        {EXAMPLES.map(ex => (
          <button
            key={ex.label}
            style={s.exBtn}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg3)'; e.currentTarget.style.color = 'var(--text)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text2)' }}
            onClick={() => onSelectExample(ex.query)}
          >
            <span style={{ color: 'var(--accent)', marginRight: '6px', fontFamily: 'var(--font-mono)' }}>›</span>
            {ex.label}
          </button>
        ))}
      </div>

      <div style={s.footer}>
        v0.1 · docker stack
      </div>
    </aside>
  )
}
