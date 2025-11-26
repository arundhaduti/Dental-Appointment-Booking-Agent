import React, { useState, useEffect, useRef } from 'react'

// Simple helper to convert YYYY-MM-DD -> DD-MM-YYYY (kept for later use)
function formatDateInputToDDMMYYYY(isoDate) {
  if (!isoDate) return ''
  const [y, m, d] = isoDate.split('-')
  return `${d}-${m}-${y}`
}

export default function App() {
  const [messages, setMessages] = useState([
    { from: 'agent', text: 'Hello - I am your dental appointment assistant. How can I help you?' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [messageHistory, setMessageHistory] = useState([]) // [{role, content}]
  const [showBookingForm, setShowBookingForm] = useState(false)
  const [bookingData, setBookingData] = useState({ name: '', date: '', time: '', reason: '', email: '', phone: '' })
  const [slotCheckResult, setSlotCheckResult] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, showBookingForm])

  const sendMessage = async () => {
    if (!input.trim()) return

    // 1) Build the *next* history explicitly (like your CLI code)
    const userTurn = { role: 'user', content: input }
    const nextHistory = [...messageHistory, userTurn]

    // 2) Update UI immediately
    const userMsg = { from: 'user', text: input }
    setMessages((m) => [...m, userMsg])
    setMessageHistory(nextHistory)
    setInput('')
    setLoading(true)

    try {
      // 3) Send the UPDATED history to backend
    const res = await fetch('http://localhost:8000/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: input }), // ✅ only message
})


      const data = await res.json()
      const reply = data.reply || data.error || 'No reply.'

      // 4) Add assistant reply to UI
      const agentMsg = { from: 'agent', text: reply }
      setMessages((m) => [...m, agentMsg])

      // 5) Also append assistant reply to history (for next turn)
      const assistantTurn = { role: 'assistant', content: reply }
      setMessageHistory((h) => [...nextHistory, assistantTurn])
    } catch (err) {
      setMessages((m) => [...m, { from: 'agent', text: 'Error contacting server.' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: '32px auto', fontFamily: 'Arial, sans-serif' }}>
      <h2>Dental Appointment Assistant</h2>
      <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12, minHeight: 400 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ margin: '8px 0', textAlign: m.from === 'user' ? 'right' : 'left' }}>
            <div
              style={{
                display: 'inline-block',
                padding: '8px 12px',
                borderRadius: 12,
                background: m.from === 'user' ? '#DCF8C6' : '#F1F0F0',
                maxWidth: '80%',
              }}
            >
              {m.text}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={{ display: 'flex', marginTop: 12 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') sendMessage()
          }}
          placeholder="Type your message..."
          style={{ flex: 1, padding: '8px 12px', borderRadius: 8, border: '1px solid #ccc' }}
        />
        <button
          onClick={sendMessage}
          disabled={loading}
          style={{ marginLeft: 8, padding: '8px 12px', borderRadius: 8 }}
        >
          {loading ? '...' : 'Send'}
        </button>
      </div>
    </div>
  )
}
