import React, { useState, useEffect, useRef } from 'react'
import './App.css'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const BOT_GREETING =
  'Hello - I am your dental appointment assistant. How can I help you?'

const LOCK_MARKER = "[CONVERSATION_LOCKED]"

// ---------- base styles ----------
const basePageStyle = {
  minHeight: '100vh',
  margin: 0,
  padding: '32px 16px',
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'flex-start',
  boxSizing: 'border-box',
  fontFamily:
    '"Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
}

const getPageStyle = (dark) => ({
  ...basePageStyle,
  background: dark
    ? 'radial-gradient(circle at top, #1f2937 0, #020617 55%, #020617 100%)'
    : 'linear-gradient(135deg, #f5f7fb 0%, #e0ecff 40%, #f5f7fb 100%)',
  color: dark ? '#e5e7eb' : '#111827',
})

const baseCardStyle = {
  width: '100%',
  maxWidth: 900,
  borderRadius: 16,
  padding: 24,
  boxSizing: 'border-box',
}

const getCardStyle = (dark) => ({
  ...baseCardStyle,
  background: dark ? '#020617' : '#ffffff',
  boxShadow: dark
    ? '0 24px 60px rgba(0, 0, 0, 0.85)'
    : '0 18px 45px rgba(15, 23, 42, 0.12)',
  border: dark ? '1px solid #111827' : '1px solid transparent',
})

const headerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 16,
}

const titleStyle = {
  fontSize: 24,
  fontWeight: 700,
  margin: 0,
}

const subtitleStyle = {
  fontSize: 13,
  marginTop: 4,
}

const headerRightStyle = {
  display: 'flex',
  gap: 8,
  alignItems: 'center',
  flexShrink: 0,
}

const chipStyle = {
  fontSize: 11,
  padding: '4px 10px',
  borderRadius: 999,
  background: '#e0f2fe',
  color: '#0369a1',
}

const resetButtonStyle = {
  fontSize: 12,
  padding: '6px 10px',
  borderRadius: 999,
  border: '1px solid #e5e7eb',
  background: '#f9fafb',
  cursor: 'pointer',
}

const darkToggleStyle = (dark) => ({
  fontSize: 12,
  padding: '6px 10px',
  borderRadius: 999,
  border: '1px solid #4b5563',
  background: '#111827',
  color: '#f9fafb',
  cursor: 'pointer',
})

const chatContainerStyle = (dark) => ({
  borderRadius: 12,
  border: `1px solid ${dark ? '#1f2937' : '#e5e7eb'}`,
  padding: 12,
  height: 460,
  overflowY: 'auto',
  background: dark ? '#020617' : '#f9fafb',
})

const inputRowStyle = {
  display: 'flex',
  gap: 8,
  marginTop: 12,
}

const textInputStyle = (dark, locked) => ({
  flex: 1,
  padding: '10px 12px',
  borderRadius: 999,
  border: `1px solid ${dark ? '#4b5563' : '#d1d5db'}`,
  outline: 'none',
  fontSize: 14,
  background: locked
    ? (dark ? '#111827' : '#e5e7eb')
    : (dark ? '#020617' : '#ffffff'),
  color: dark ? '#e5e7eb' : '#111827',
  opacity: locked ? 0.6 : 1,
})

const sendButtonStyle = (disabled) => ({
  padding: '10px 18px',
  borderRadius: 999,
  border: 'none',
  background: disabled ? '#9ca3af' : '#2563eb',
  color: '#ffffff',
  fontWeight: 600,
  fontSize: 14,
  cursor: disabled ? 'not-allowed' : 'pointer',
  minWidth: 80,
})

const bubbleRowStyle = (fromUser) => ({
  margin: '8px 0',
  display: 'flex',
  justifyContent: fromUser ? 'flex-end' : 'flex-start',
})

const bubbleInnerRowStyle = (fromUser) => ({
  display: 'flex',
  flexDirection: fromUser ? 'row-reverse' : 'row',
  alignItems: 'flex-end',
  gap: 8,
})

const avatarStyle = {
  width: 32,
  height: 32,
  borderRadius: 999,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: 18,
}

const avatarBotStyle = (dark) => ({
  ...avatarStyle,
  background: dark ? '#0f172a' : '#e0f2fe',
})

const avatarUserStyle = (dark) => ({
  ...avatarStyle,
  background: dark ? '#14532d' : '#bbf7d0',
})

const bubbleStyle = (fromUser, dark) => ({
  display: 'inline-block',
  padding: '9px 13px',
  borderRadius: 16,
  maxWidth: '78%',
  fontSize: 14,
  lineHeight: 1.5,
  background: fromUser
    ? dark
      ? '#14532d'
      : '#d9f99d'
    : dark
    ? '#020617'
    : '#f3f4f6',
  color: dark ? '#e5e7eb' : '#111827',
  border: fromUser
    ? dark
      ? '1px solid #16a34a'
      : '1px solid #bef264'
    : dark
    ? '1px solid #111827'
    : '1px solid #e5e7eb',
})

// ---------- component ----------
export default function App() {
  const [messages, setMessages] = useState([
    { from: 'agent', text: BOT_GREETING },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [darkMode, setDarkMode] = useState(false)
  const [locked, setLocked] = useState(false)  // 🔒 NEW
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, locked])

  const sendMessage = async () => {
    if (!input.trim() || loading || locked) return

    const userText = input.trim()
    const userMsg = { from: 'user', text: userText }

    setMessages((m) => [...m, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userText }),
      })

      const data = await res.json()
      let reply = data.reply || data.error || 'No reply.'

      // 🔒 Detect lock marker
      if (reply.startsWith(LOCK_MARKER)) {
        setLocked(true)
        reply = reply.replace(LOCK_MARKER, '').trim()
      }

      const agentMsg = { from: 'agent', text: reply }
      setMessages((m) => [...m, agentMsg])
    } catch (err) {
      setMessages((m) => [
        ...m,
        { from: 'agent', text: 'Error contacting server.' },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      sendMessage()
    }
  }

  const handleReset = async () => {
    setMessages([{ from: 'agent', text: BOT_GREETING }])
    setInput('')
    setLoading(false)
    setLocked(false)   // 🔓 unlock

    try {
      await fetch('http://localhost:8000/reset', { method: 'POST' })
    } catch {}
  }

  const toggleDarkMode = () => setDarkMode((d) => !d)

  return (
    <div
      className={darkMode ? 'app-root dark' : 'app-root'}
      style={getPageStyle(darkMode)}
    >
      <div style={getCardStyle(darkMode)}>
        <header style={headerStyle}>
          <div>
            <h2 style={titleStyle}>Dental Appointment Assistant</h2>
            <p
              style={{
                ...subtitleStyle,
                color: darkMode ? '#9ca3af' : '#6b7280',
              }}
            >
              Chat with the assistant to schedule or adjust your dental visit.
            </p>
          </div>
          <div style={headerRightStyle}>
            <span style={chipStyle}>LLM-powered</span>
            <button
              type="button"
              style={darkToggleStyle(darkMode)}
              onClick={toggleDarkMode}
            >
              {darkMode ? '☀ Light' : '🌙 Dark'}
            </button>
            <button
              type="button"
              style={resetButtonStyle}
              onClick={handleReset}
            >
              ⟲ Start over
            </button>
          </div>
        </header>

        {/* 🔒 LOCKOUT BANNER */}
        {locked && (
          <div
            style={{
              padding: '10px 14px',
              marginBottom: 10,
              borderRadius: 8,
              background: '#fee2e2',
              border: '1px solid #fecaca',
              color: '#b91c1c',
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            Conversation locked due to repeated violations.  
            Click **Start over** to begin a new session.
          </div>
        )}

        <div style={chatContainerStyle(darkMode)}>
          {messages.map((m, i) => (
            <div key={i} style={bubbleRowStyle(m.from === 'user')}>
              <div style={bubbleInnerRowStyle(m.from === 'user')}>
                <div
                  style={
                    m.from === 'user'
                      ? avatarUserStyle(darkMode)
                      : avatarBotStyle(darkMode)
                  }
                >
                  {m.from === 'user' ? '🧑' : '🦷'}
                </div>
                <div
                  className="bubble-enter"
                  style={bubbleStyle(m.from === 'user', darkMode)}
                >
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      p: (props) => (
                        <p style={{ margin: '6px 0' }} {...props} />
                      ),
                      strong: (props) => (
                        <strong style={{ fontWeight: 700 }} {...props} />
                      ),
                      li: (props) => (
                        <li style={{ marginBottom: 4 }} {...props} />
                      ),
                    }}
                  >
                    {m.text}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div style={bubbleRowStyle(false)}>
              <div style={bubbleInnerRowStyle(false)}>
                <div style={avatarBotStyle(darkMode)}>🦷</div>
                <div className="typing-indicator">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div style={inputRowStyle}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              locked ? "Conversation locked. Click Start over." : "Type your message..."
            }
            disabled={loading || locked}
            style={textInputStyle(darkMode, locked)}
          />
          <button
            type="button"
            onClick={sendMessage}
            disabled={loading || !input.trim() || locked}
            style={sendButtonStyle(loading || !input.trim() || locked)}
          >
            {locked ? 'Locked' : loading ? '...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
