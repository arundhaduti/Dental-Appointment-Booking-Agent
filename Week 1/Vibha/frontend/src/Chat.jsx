import { useState, useEffect, useRef } from "react";
import { sendMessage, resetChat } from "./api";
import "./styles.css";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  // 🔹 Show greeting when chat opens
  useEffect(() => {
    setMessages([
      {
        sender: "bot",
        text: "🦷 Hello! Need to book or modify an appointment today?",
      },
    ]);
  }, []);

  const handleReset = async () => {
    await resetChat(); // backend reset
    setMessages([
      {
        sender: "bot",
        text: "🦷 Hello! Need to book or modify an appointment today?",
      },
    ]);
  };

  const send = async () => {
    if (!input.trim()) return;

    setMessages((prev) => [...prev, { sender: "user", text: input }]);
    setInput("");
    setLoading(true);

    const res = await sendMessage(input);

    setMessages((prev) => [...prev, { sender: "bot", text: res.data.reply }]);
    setLoading(false);
  };

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="chat-container">
      <div className="header">🦷 Dental Assistant</div>

      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.sender}`}>
            {m.text}
          </div>
        ))}

        {loading && <div className="msg bot bot-typing">Typing…</div>}

        <div ref={bottomRef}></div>
      </div>

      <div className="input-area">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type to book your appointment..."
        />
        <button onClick={send}>Send</button>
        <button onClick={handleReset}>Reset</button>
      </div>
    </div>
  );
}
