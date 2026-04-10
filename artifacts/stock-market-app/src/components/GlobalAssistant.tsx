import { useState, useRef, useEffect, useCallback } from "react";
import { fetchApi } from "@/lib/api";
import {
  Bot, Send, X, Minimize2, Maximize2, RotateCcw,
  Sparkles, ChevronDown,
} from "lucide-react";

interface Msg { role: "user" | "assistant"; content: string }

const SUGGESTED = [
  "Which sectors are up today?",
  "Where is money flowing?",
  "Analyse RELIANCE",
  "Show bullish patterns",
  "What is RSI?",
  "Run golden cross scanner",
];

// ── Minimal markdown → JSX renderer (bold, bullet lists, headers) ─────────────
function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];

  function renderInline(s: string, key: number) {
    const parts = s.split(/(\*\*[^*]+\*\*)/g);
    return (
      <span key={key}>
        {parts.map((p, i) =>
          p.startsWith("**") && p.endsWith("**")
            ? <strong key={i}>{p.slice(2, -2)}</strong>
            : p
        )}
      </span>
    );
  }

  lines.forEach((line, i) => {
    if (!line.trim()) {
      nodes.push(<div key={i} className="h-2" />);
    } else if (line.startsWith("## ")) {
      nodes.push(
        <h3 key={i} className="font-bold text-[13px] mt-1 mb-0.5">
          {renderInline(line.slice(3), i)}
        </h3>
      );
    } else if (line.startsWith("**") && line.endsWith("**") && line.length > 4) {
      nodes.push(
        <p key={i} className="font-semibold text-[12px] leading-snug">
          {renderInline(line, i)}
        </p>
      );
    } else if (line.startsWith("- ") || line.startsWith("• ")) {
      nodes.push(
        <div key={i} className="flex gap-1.5 text-[12px] leading-snug">
          <span className="mt-[3px] flex-shrink-0 w-1 h-1 rounded-full bg-current opacity-60 self-start translate-y-[5px]" />
          <span>{renderInline(line.slice(2), i)}</span>
        </div>
      );
    } else if (line.startsWith("| ")) {
      nodes.push(
        <div key={i} className="text-[11px] font-mono opacity-80 leading-snug">
          {line}
        </div>
      );
    } else if (line.startsWith("*") && line.endsWith("*")) {
      nodes.push(
        <p key={i} className="text-[11px] italic opacity-70 leading-snug">
          {line.slice(1, -1)}
        </p>
      );
    } else {
      nodes.push(
        <p key={i} className="text-[12px] leading-snug">
          {renderInline(line, i)}
        </p>
      );
    }
  });

  return <div className="space-y-[3px]">{nodes}</div>;
}

export default function GlobalAssistant() {
  const [open, setOpen]       = useState(false);
  const [wide, setWide]       = useState(false);
  const [msgs, setMsgs]       = useState<Msg[]>([]);
  const [input, setInput]     = useState("");
  const [loading, setLoading] = useState(false);
  const [dot, setDot]         = useState(0);
  const endRef   = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Animate "thinking" dots
  useEffect(() => {
    if (!loading) return;
    const t = setInterval(() => setDot(d => (d + 1) % 4), 420);
    return () => clearInterval(t);
  }, [loading]);

  // Auto-scroll
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, loading]);

  // Focus input when opened
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open]);

  const send = useCallback(async (text: string) => {
    const t = text.trim();
    if (!t || loading) return;
    setMsgs(prev => [...prev, { role: "user", content: t }]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetchApi<{ reply: string }>("/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: t }),
      });
      setMsgs(prev => [...prev, { role: "assistant", content: res.reply }]);
    } catch (e: any) {
      setMsgs(prev => [
        ...prev,
        { role: "assistant", content: "Sorry, I couldn't reach the server right now. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }, [loading]);

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  }

  const isEmpty = msgs.length === 0;

  // ── Panel width ──────────────────────────────────────────────────────────────
  const panelW = wide ? "w-[480px]" : "w-[350px]";

  return (
    <>
      {/* ── Floating button ────────────────────────────────────────────────────── */}
      <button
        aria-label="Open AI assistant"
        onClick={() => setOpen(o => !o)}
        className={`
          fixed bottom-5 right-5 z-[9999]
          w-13 h-13 rounded-full shadow-xl
          flex items-center justify-center
          transition-all duration-200
          ${open
            ? "bg-gray-700 dark:bg-gray-600 scale-90"
            : "bg-indigo-600 hover:bg-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-400 scale-100 hover:scale-105"
          }
        `}
        style={{ width: 52, height: 52 }}
      >
        {open
          ? <X className="w-5 h-5 text-white" />
          : (
            <>
              <Bot className="w-6 h-6 text-white" />
              {/* unread dot when closed & has msgs */}
              {msgs.length > 0 && (
                <span className="absolute top-0.5 right-0.5 w-3 h-3 bg-emerald-400 rounded-full border-2 border-white dark:border-gray-900" />
              )}
            </>
          )
        }
      </button>

      {/* ── Chat panel ────────────────────────────────────────────────────────── */}
      {open && (
        <div
          className={`
            fixed bottom-[72px] right-5 z-[9998]
            ${panelW}
            max-h-[calc(100vh-120px)]
            flex flex-col
            bg-white dark:bg-gray-900
            border border-gray-200 dark:border-white/10
            rounded-2xl shadow-2xl
            overflow-hidden
            transition-all duration-200
          `}
        >
          {/* Header */}
          <div className="flex items-center gap-2.5 px-4 py-3 bg-indigo-600 dark:bg-indigo-700 flex-shrink-0">
            <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white font-semibold text-sm leading-none">Market Assistant</p>
              <p className="text-indigo-200 text-[10px] mt-0.5 leading-none">
                {loading ? "Thinking" + ".".repeat(dot + 1) : "Ask anything about Indian stocks"}
              </p>
            </div>
            <div className="flex items-center gap-1">
              {msgs.length > 0 && (
                <button
                  onClick={() => setMsgs([])}
                  title="Clear chat"
                  className="p-1.5 rounded-lg text-indigo-200 hover:text-white hover:bg-white/10 transition"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              )}
              <button
                onClick={() => setWide(w => !w)}
                title={wide ? "Compact" : "Expand"}
                className="p-1.5 rounded-lg text-indigo-200 hover:text-white hover:bg-white/10 transition hidden sm:flex"
              >
                {wide ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
              </button>
              <button
                onClick={() => setOpen(false)}
                title="Close"
                className="p-1.5 rounded-lg text-indigo-200 hover:text-white hover:bg-white/10 transition"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">

            {/* Empty state */}
            {isEmpty && (
              <div className="flex flex-col items-center text-center pt-4 pb-2 px-2">
                <div className="w-12 h-12 rounded-2xl bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center mb-3">
                  <Sparkles className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                </div>
                <p className="font-semibold text-gray-800 dark:text-white text-sm">
                  Hi! I'm your Market Assistant
                </p>
                <p className="text-gray-500 dark:text-gray-400 text-xs mt-1 leading-relaxed">
                  Ask me anything about Indian stocks, sectors, patterns, or how the market works — in plain English.
                </p>

                {/* Suggested questions */}
                <div className="mt-4 w-full space-y-1.5">
                  {SUGGESTED.map(q => (
                    <button
                      key={q}
                      onClick={() => send(q)}
                      className="w-full text-left text-xs px-3 py-2 rounded-xl
                        bg-gray-50 dark:bg-gray-800
                        border border-gray-200 dark:border-white/10
                        text-gray-700 dark:text-gray-300
                        hover:bg-indigo-50 dark:hover:bg-indigo-500/10
                        hover:border-indigo-200 dark:hover:border-indigo-500/40
                        hover:text-indigo-700 dark:hover:text-indigo-300
                        transition"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Conversation */}
            {msgs.map((m, i) => (
              <div key={i} className={`flex gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "assistant" && (
                  <div className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Bot className="w-3.5 h-3.5 text-white" />
                  </div>
                )}
                <div
                  className={`
                    max-w-[82%] rounded-2xl px-3 py-2.5
                    ${m.role === "user"
                      ? "bg-indigo-600 text-white rounded-tr-sm"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-tl-sm"
                    }
                  `}
                >
                  {m.role === "user"
                    ? <p className="text-[12px] leading-snug">{m.content}</p>
                    : <Markdown text={m.content} />
                  }
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {loading && (
              <div className="flex gap-2 justify-start">
                <div className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot className="w-3.5 h-3.5 text-white" />
                </div>
                <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-tl-sm px-3 py-2.5">
                  <div className="flex gap-1 items-center h-4">
                    {[0,1,2].map(i => (
                      <span
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-indigo-400 dark:bg-indigo-500 animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div ref={endRef} />
          </div>

          {/* Input area */}
          <div className="flex-shrink-0 p-3 border-t border-gray-100 dark:border-white/[0.06] bg-white dark:bg-gray-900">
            <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 focus-within:border-indigo-400 dark:focus-within:border-indigo-500 transition">
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Ask a question…"
                disabled={loading}
                className="flex-1 bg-transparent text-sm text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 outline-none min-w-0"
              />
              <button
                onClick={() => send(input)}
                disabled={!input.trim() || loading}
                className="flex-shrink-0 w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition"
              >
                <Send className="w-3.5 h-3.5 text-white" />
              </button>
            </div>
            <p className="text-[10px] text-gray-400 dark:text-gray-600 text-center mt-1.5">
              Rule-based assistant · No AI API cost · Indian markets only
            </p>
          </div>
        </div>
      )}
    </>
  );
}
