import { useState } from 'react'

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
  toolSection: {
    marginTop: '10px',
    maxWidth: '72%',
  },
  toolToggle: {
    background: 'none',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    color: 'var(--accent3)',
    fontFamily: 'var(--font-mono)',
    fontSize: '11px',
    padding: '4px 10px',
    cursor: 'pointer',
    letterSpacing: '0.06em',
  },
  toolList: {
    marginTop: '8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  toolCall: {
    background: 'var(--bg3)',
    border: '1px solid var(--border)',
    borderLeft: '2px solid var(--accent3)',
    borderRadius: 'var(--radius)',
    padding: '8px 12px',
    fontFamily: 'var(--font-mono)',
    fontSize: '11px',
    color: 'var(--text2)',
  },
  toolName: {
    color: 'var(--accent3)',
    fontWeight: 500,
    marginBottom: '4px',
  },
  toolJson: {
    color: 'var(--text3)',
    fontSize: '10px',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
    maxHeight: '120px',
    overflowY: 'auto',
  },
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
  const [showTools, setShowTools] = useState(false)
  const { role, content, toolCalls } = msg

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

      {/* Tool call audit trail */}
      {role === 'assistant' && toolCalls?.length > 0 && (
        <div style={s.toolSection}>
          <button
            style={s.toolToggle}
            onClick={() => setShowTools(v => !v)}
          >
            {showTools ? '▾' : '▸'} {toolCalls.length} tool call{toolCalls.length > 1 ? 's' : ''}
          </button>
          {showTools && (
            <div style={s.toolList}>
              {toolCalls.map((tc, i) => (
                <div key={i} style={s.toolCall}>
                  <div style={s.toolName}>{tc.tool}</div>
                  <div style={{ marginBottom: '4px', fontSize: '10px', color: 'var(--text3)' }}>input</div>
                  <div style={s.toolJson}>{JSON.stringify(tc.input, null, 2)}</div>
                  {tc.result && (
                    <>
                      <div style={{ marginTop: '6px', marginBottom: '4px', fontSize: '10px', color: 'var(--accent2)' }}>result</div>
                      <div style={s.toolJson}>{JSON.stringify(tc.result, null, 2)}</div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
