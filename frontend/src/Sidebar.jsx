const EXAMPLES = [
  { label: 'Explain a result', query: 'Explain what tensile strength means in simple terms.' },
  { label: 'Summarise text', query: 'Summarise the difference between tensile strength and elongation.' },
  { label: 'Draft an email', query: 'Write a short email asking a colleague for the latest material test results.' },
  { label: 'Brainstorm ideas', query: 'Give me five ideas for improving a material testing workflow.' },
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
        v0.1 · simple chat stack
      </div>
    </aside>
  )
}
