import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useState, useRef, useEffect } from "react";
import { MessageCircle, Send, Bot, User, Wifi, WifiOff } from "lucide-react";

const QUICK_COMMANDS = [
  "!help", "!sectors", "!rotation", "!patterns", "!scan",
  "!analyze RELIANCE", "!analyze TCS", "!entry HDFCBANK", "!scanner list", "!status",
];

export default function WhatsAppBot({ embedded = false }: { embedded?: boolean }) {
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const { data: status } = useQuery({
    queryKey: ["whatsapp-status"],
    queryFn: api.whatsappStatus,
    refetchInterval: 30000,
  });

  const sendMut = useMutation({
    mutationFn: ({ msg }: { msg: string }) =>
      api.whatsappMessage("web-user", msg),
    onSuccess: (data) => {
      setMessages(prev => [...prev, { from: "web-user", text: data.text, timestamp: data.timestamp, isUser: true }, { from: "bot", text: data.response, timestamp: data.timestamp, isUser: false }]);
    },
  });

  useEffect(() => {
    if (messages.length === 0) return;
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function send(msg?: string) {
    const m = msg || input.trim();
    if (!m) return;
    setInput("");
    sendMut.mutate({ msg: m });
  }

  return (
    <div className="space-y-6">
      {!embedded && (
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">WhatsApp Bot</h1>
            <p className="text-sm text-gray-500">Test and preview bot responses before connecting to WhatsApp</p>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm">
            {status?.enabled ? (
              <>
                <Wifi className="w-4 h-4 text-green-500" />
                <span className="text-green-600 font-medium">{status.status}</span>
              </>
            ) : (
              <>
                <WifiOff className="w-4 h-4 text-gray-400" />
                <span className="text-gray-500">DISABLED</span>
              </>
            )}
          </div>
        </div>
      )}

      {status && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 text-center">
            <p className="text-lg font-bold text-gray-900">{status.totalMessages || 0}</p>
            <p className="text-xs text-gray-500">Messages</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 text-center">
            <p className="text-lg font-bold text-gray-900">{status.capabilities?.length || 0}</p>
            <p className="text-xs text-gray-500">Capabilities</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 text-center col-span-2">
            <p className="text-xs font-medium text-gray-600 mb-1">Bot Commands</p>
            <p className="text-xs text-gray-500">{status.commands?.join(" • ")}</p>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="bg-green-600 text-white px-4 py-3 flex items-center gap-2">
          <MessageCircle className="w-5 h-5" />
          <div>
            <p className="font-medium text-sm">WhatsApp Bot Preview</p>
            <p className="text-xs text-green-200">Test your bot commands here</p>
          </div>
        </div>

        <div className="h-72 overflow-y-auto p-4 bg-gray-50 space-y-3">
          {messages.length === 0 && (
            <div className="text-center py-8 text-gray-400">
              <Bot className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Send a command to test the bot</p>
              <p className="text-xs mt-1">Try "!help" to see all commands</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex items-end gap-2 ${m.isUser ? "flex-row-reverse" : ""}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${m.isUser ? "bg-indigo-600" : "bg-green-600"}`}>
                {m.isUser ? <User className="w-3 h-3 text-white" /> : <Bot className="w-3 h-3 text-white" />}
              </div>
              <div className={`max-w-xs rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${m.isUser ? "bg-indigo-600 text-white rounded-br-sm" : "bg-white text-gray-800 shadow-sm rounded-bl-sm border border-gray-100"}`}>
                {m.text}
              </div>
            </div>
          ))}
          {sendMut.isPending && (
            <div className="flex items-end gap-2">
              <div className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 bg-green-600">
                <Bot className="w-3 h-3 text-white" />
              </div>
              <div className="bg-white rounded-2xl rounded-bl-sm border border-gray-100 px-3 py-2 shadow-sm">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{animationDelay:"0ms"}} />
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{animationDelay:"150ms"}} />
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{animationDelay:"300ms"}} />
                </div>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="p-3 border-t border-gray-200">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && send()}
              placeholder="Type a command... (e.g., !analyze RELIANCE)"
              className="flex-1 px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-green-300"
            />
            <button
              onClick={() => send()}
              disabled={sendMut.isPending || !input.trim()}
              className="px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-60 transition"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
        <p className="text-xs font-medium text-gray-500 uppercase mb-3">Quick Commands</p>
        <div className="flex flex-wrap gap-2">
          {QUICK_COMMANDS.map(cmd => (
            <button
              key={cmd}
              onClick={() => send(cmd)}
              disabled={sendMut.isPending}
              className="text-xs px-3 py-1.5 rounded-full bg-gray-100 text-gray-700 hover:bg-green-50 hover:text-green-700 hover:border-green-200 border border-transparent transition"
            >
              {cmd}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-amber-800 mb-2">Production WhatsApp Integration</h3>
        <p className="text-xs text-amber-700 leading-relaxed">
          This dashboard simulates the WhatsApp bot. For real WhatsApp integration, deploy on a VPS with <code className="bg-amber-100 px-1 rounded">whatsapp-web.js</code> and Chromium/Puppeteer.
          The bot processes the same commands shown here. Use the <code className="bg-amber-100 px-1 rounded">POST /api/whatsapp/message</code> endpoint for webhook integration.
        </p>
      </div>
    </div>
  );
}
