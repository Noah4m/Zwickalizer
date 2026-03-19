const s = {
  row: (role) => ({
    display: 'flex',
    flexDirection: 'column',
    alignItems: role === 'user' ? 'flex-end' : 'flex-start',
    maxWidth: '100%',
  }),
  bubble: (role) => ({
    maxWidth: '72%',
    padding: '12px 16px',
    borderRadius: role === 'user' ? '10px 10px 2px 10px' : '2px 10px 10px 10px',
    background: role === 'user' ? 'var(--bg3)' : 'var(--bg2)',
    border: `1px solid ${role === 'user' ? 'var(--border2)' : 'var(--border)'}`,
    color: 'var(--text)',
    fontSize: '14px',
    lineHeight: 1.7,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  }),
  roleLabel: (role) => ({
    fontSize: '10px',
    fontFamily: 'var(--font-mono)',
    color: role === 'user' ? 'var(--text3)' : 'var(--accent)',
    marginBottom: '5px',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    paddingLeft: role === 'user' ? 0 : '2px',
  }),
  loading: {
    display: 'flex',
    gap: '5px',
    alignItems: 'center',
    padding: '14px 16px',
    background: 'var(--bg2)',
    border: '1px solid var(--border)',
    borderRadius: '2px 10px 10px 10px',
  },
  dot: (i) => ({
    width: '6px', height: '6px',
    borderRadius: '50%',
    background: 'var(--accent)',
    animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
  }),
}

// Inline keyframes via a style tag (once)
if (!document.getElementById('matai-anim')) {
  const el = document.createElement('style')
  el.id = 'matai-anim'
  el.textContent = `
    @keyframes pulse {
      0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
      40% { opacity: 1; transform: scale(1); }
    }
  `
  document.head.appendChild(el)
}

export default function Message({ msg, loading }) {
  const { role, content } = msg

  if (loading) {
    return (
      <div style={s.row('assistant')}>
        <div style={s.roleLabel('assistant')}>agent</div>
        <div style={s.loading}>
          {[0, 1, 2].map(i => <div key={i} style={s.dot(i)} />)}
        </div>
      </div>
    )
  }

  return (
    <div style={s.row(role)}>
      <div style={s.roleLabel(role)}>{role === 'user' ? 'you' : 'agent'}</div>
      <div style={s.bubble(role)}>{content}</div>
    </div>
  )
}
