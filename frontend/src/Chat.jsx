import { useState, useEffect, useRef } from 'react'
import Message from './Message.jsx'

const BACKEND = import.meta.env.VITE_BACKEND_URL || ''

const s = {
  wrap: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: 'var(--bg)',
  },
  header: {
    padding: '14px 24px',
    borderBottom: '1px solid var(--border)',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    background: 'var(--bg)',
    flexShrink: 0,
  },
  headerDot: {
    width: '7px', height: '7px',
    borderRadius: '50%',
    background: 'var(--accent)',
    boxShadow: '0 0 6px var(--accent)',
  },
  headerTitle: {
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    color: 'var(--text2)',
  },
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: '24px',
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  empty: {
    margin: 'auto',
    textAlign: 'center',
    color: 'var(--text3)',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
    lineHeight: 2,
  },
  emptyBig: {
    fontSize: '28px',
    fontWeight: 300,
    color: 'var(--border2)',
    fontFamily: 'var(--font-mono)',
    marginBottom: '8px',
  },
  inputRow: {
    padding: '16px 24px',
    borderTop: '1px solid var(--border)',
    display: 'flex',
    gap: '10px',
    flexShrink: 0,
    background: 'var(--bg2)',
  },
  textarea: {
    flex: 1,
    background: 'var(--bg3)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    color: 'var(--text)',
    fontFamily: 'var(--font-sans)',
    fontSize: '14px',
    padding: '10px 14px',
    resize: 'none',
    outline: 'none',
    lineHeight: 1.5,
    transition: 'border-color 0.15s',
  },
  sendBtn: {
    background: 'var(--accent)',
    border: 'none',
    borderRadius: 'var(--radius)',
    color: '#0d0f11',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
    fontWeight: 500,
    padding: '0 18px',
    cursor: 'pointer',
    transition: 'opacity 0.15s',
    flexShrink: 0,
    letterSpacing: '0.05em',
  },
}

export default function Chat({ exampleQuery, onExampleConsumed }) {
  const [history, setHistory] = useState([])   // {role, content, toolCalls?}
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const taRef = useRef(null)

  // Fill input when sidebar example clicked
  useEffect(() => {
    if (exampleQuery) {
      setInput(exampleQuery)
      taRef.current?.focus()
      onExampleConsumed()
    }
  }, [exampleQuery])

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, loading])

  async function send() {
    const text = input.trim()
    if (!text || loading) return

    const userMsg = { role: 'user', content: text }
    const newHistory = [...history, userMsg]
    setHistory(newHistory)
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`${BACKEND}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          history: history.map(m => ({ role: m.role, content: m.content })),
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setHistory([...newHistory, {
        role: 'assistant',
        content: data.answer,
        toolCalls: data.tool_calls || [],
      }])
    } catch (err) {
      setHistory([...newHistory, {
        role: 'assistant',
        content: `⚠ Error: ${err.message}`,
        toolCalls: [],
      }])
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div style={s.wrap}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.headerDot} />
        <span style={s.headerTitle}>agent connected · claude-opus</span>
      </div>

      {/* Messages */}
      <div style={s.messages}>
        {history.length === 0 && (
          <div style={s.empty}>
            <div style={s.emptyBig}>MAT//AI</div>
            ask about your test data
          </div>
        )}
        {history.map((msg, i) => (
          <Message key={i} msg={msg} />
        ))}
        {loading && <Message msg={{ role: 'assistant', content: null, toolCalls: [] }} loading />}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={s.inputRow}>
        <textarea
          ref={taRef}
          style={s.textarea}
          rows={2}
          placeholder="Ask about materials, trends, comparisons…   ↵ send  ⇧↵ newline"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={e => e.target.style.borderColor = 'var(--border2)'}
          onBlur={e => e.target.style.borderColor = 'var(--border)'}
        />
        <button
          style={{ ...s.sendBtn, opacity: loading ? 0.5 : 1 }}
          onClick={send}
          disabled={loading}
        >
          SEND
        </button>
      </div>
    </div>
  )
}
