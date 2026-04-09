import { useEffect, useRef, useState, useCallback } from "react";
import { X, Send, MessageCircle, Wifi, WifiOff } from "lucide-react";

export interface ChatMessage {
  id: string;
  symbol: string;
  username: string;
  text: string;
  timestamp: string;
}

interface StockChatProps {
  symbol: string;
  onClose: () => void;
}

function getOrCreateUsername(): string {
  const key = "nifty-chat-username";
  let name = localStorage.getItem(key);
  if (!name) {
    const adjectives = ["Bull", "Bear", "Alpha", "Nifty", "Smart", "Quick", "Ace", "Pro"];
    const nouns = ["Trader", "Analyst", "Investor", "Scout", "Hawk", "Wolf", "Fox", "Eagle"];
    const num = Math.floor(Math.random() * 900) + 100;
    name = `${adjectives[Math.floor(Math.random() * adjectives.length)]}${nouns[Math.floor(Math.random() * nouns.length)]}${num}`;
    localStorage.setItem(key, name);
  }
  return name;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export default function StockChat({ symbol, onClose }: StockChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const username = useRef(getOrCreateUsername()).current;

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (!symbol) return;

    fetch(`/api/chat/history/${encodeURIComponent(symbol)}`)
      .then(r => r.json())
      .then(d => {
        if (Array.isArray(d.messages)) setMessages(d.messages);
      })
      .catch(() => {});

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/chat/ws/${encodeURIComponent(symbol)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => { setConnected(true); setError(null); };
    ws.onclose = () => { setConnected(false); };
    ws.onerror = () => { setError("Connection failed — retrying…"); setConnected(false); };
    ws.onmessage = (evt) => {
      try {
        const msg: ChatMessage = JSON.parse(evt.data);
        setMessages(prev => [...prev, msg]);
      } catch {}
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [symbol]);

  function sendMessage() {
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ username, text }));
    setInput("");
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="fixed right-0 top-0 bottom-0 z-50 flex flex-col w-80 md:w-96 bg-white border-l border-gray-200 shadow-2xl">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 py-3 border-b border-gray-100 bg-indigo-600 text-white flex-shrink-0">
        <MessageCircle className="w-4 h-4 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="font-bold text-sm truncate">{symbol} Chat</p>
          <p className="text-xs text-indigo-200 truncate">as {username}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {connected
            ? <Wifi className="w-3.5 h-3.5 text-green-300" title="Connected" />
            : <WifiOff className="w-3.5 h-3.5 text-red-300" title="Disconnected" />
          }
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-indigo-700 transition"
            title="Close chat"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Error bar */}
      {error && (
        <div className="px-4 py-2 bg-red-50 border-b border-red-100 text-xs text-red-600 flex-shrink-0">
          {error}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 text-center">
            <MessageCircle className="w-10 h-10 opacity-20 mb-2" />
            <p className="text-sm font-medium">No messages yet</p>
            <p className="text-xs mt-1">Be the first to discuss {symbol}!</p>
          </div>
        )}

        {messages.map((msg) => {
          const isOwn = msg.username === username;
          return (
            <div key={msg.id} className={`flex flex-col ${isOwn ? "items-end" : "items-start"}`}>
              <div className="flex items-baseline gap-1.5 mb-0.5">
                <span className={`text-xs font-semibold ${isOwn ? "text-indigo-600" : "text-gray-600"}`}>
                  {isOwn ? "You" : msg.username}
                </span>
                <span className="text-xs text-gray-400">{formatTime(msg.timestamp)}</span>
              </div>
              <div className={`max-w-[85%] px-3 py-2 rounded-2xl text-sm leading-relaxed break-words ${
                isOwn
                  ? "bg-indigo-600 text-white rounded-tr-sm"
                  : "bg-gray-100 text-gray-800 rounded-tl-sm"
              }`}>
                {msg.text}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-100 px-3 py-3 flex-shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={connected ? `Message #${symbol.toLowerCase()}…` : "Connecting…"}
            disabled={!connected}
            rows={1}
            className="flex-1 resize-none border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:opacity-50 min-h-[40px] max-h-28 leading-5"
            style={{ overflowY: "auto" }}
          />
          <button
            onClick={sendMessage}
            disabled={!connected || !input.trim()}
            className="p-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-40 transition flex-shrink-0"
            title="Send (Enter)"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1.5 text-center">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  );
}
