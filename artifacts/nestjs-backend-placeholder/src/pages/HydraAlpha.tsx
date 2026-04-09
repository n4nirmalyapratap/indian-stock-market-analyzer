import { useState, useRef, useEffect } from "react";
import { fetchApi } from "@/lib/api";
import {
  Brain, Zap, BarChart3, Shield, TrendingUp, TrendingDown,
  Minus, Send, RefreshCw, ChevronDown, ChevronUp, Info,
  Target, Activity, AlertTriangle, CheckCircle2, XCircle,
  Search, Play, Database
} from "lucide-react";

const JSON_HEADERS = { "Content-Type": "application/json" };
function hGet<T = any>(path: string) { return fetchApi<T>(path); }
function hPost<T = any>(path: string, body: unknown) {
  return fetchApi<T>(path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
}

// ── Types ─────────────────────────────────────────────────────────────────────
type Tab = "supervisor" | "pairs" | "backtest" | "var" | "forecast";

interface ChatMessage { role: "user" | "hydra"; text: string; data?: any; time: string; }

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmt(n: any, dec = 2) {
  if (n == null || isNaN(Number(n))) return "—";
  const v = Number(n);
  return (v >= 0 ? "+" : "") + v.toFixed(dec);
}
function fmtN(n: any, dec = 2) {
  if (n == null || isNaN(Number(n))) return "—";
  return Number(n).toFixed(dec);
}
function fmtINR(n: any) {
  if (n == null) return "—";
  const raw = Number(n);
  const sign = raw < 0 ? "-" : "";
  const v = Math.abs(raw);
  if (v >= 1e7) return `${sign}₹${(v / 1e7).toFixed(2)}Cr`;
  if (v >= 1e5) return `${sign}₹${(v / 1e5).toFixed(2)}L`;
  return `${sign}₹${v.toLocaleString("en-IN")}`;
}

function SignalBadge({ signal }: { signal: string }) {
  const cfg: Record<string, { color: string; label: string }> = {
    LONG_SPREAD:    { color: "bg-green-600 text-white", label: "↑ LONG SPREAD" },
    SHORT_SPREAD:   { color: "bg-red-600 text-white",   label: "↓ SHORT SPREAD" },
    EXIT:           { color: "bg-yellow-500 text-white", label: "↩ EXIT" },
    HOLD:           { color: "bg-gray-400 text-white",  label: "⏸ HOLD" },
    NO_TRADE:       { color: "bg-gray-300 text-gray-700", label: "— NO TRADE" },
    BULLISH:        { color: "bg-green-600 text-white", label: "↑ BULLISH" },
    BEARISH:        { color: "bg-red-600 text-white",   label: "↓ BEARISH" },
    NEUTRAL:        { color: "bg-gray-400 text-white",  label: "→ NEUTRAL" },
  };
  const c = cfg[signal] || { color: "bg-gray-300 text-gray-700", label: signal };
  return <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${c.color}`}>{c.label}</span>;
}

// ── Mini sparkline (SVG) ──────────────────────────────────────────────────────
function Sparkline({ data, color = "#6366f1", height = 40, width = 200 }: {
  data: number[]; color?: string; height?: number; width?: number
}) {
  if (!data || data.length < 2) return <div className="text-gray-400 text-xs">No chart data</div>;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} />
      <circle cx={(data.length - 1) / (data.length - 1) * width}
              cy={height - ((data[data.length - 1] - min) / range) * height}
              r={3} fill={color} />
    </svg>
  );
}

// ── Gauge component ───────────────────────────────────────────────────────────
function Gauge({ value, min = -5, max = 5, label }: { value: number; min?: number; max?: number; label: string }) {
  const pct = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const angle = -90 + pct * 180;
  const r = 36;
  const cx = 50; const cy = 50;
  const x = cx + r * Math.cos((angle * Math.PI) / 180);
  const y = cy + r * Math.sin((angle * Math.PI) / 180);
  const color = value < -2 ? "#dc2626" : value < -0.5 ? "#f97316" : value > 2 ? "#16a34a" : value > 0.5 ? "#22c55e" : "#6b7280";
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 100 60" width={100} height={60}>
        <path d="M14,50 A36,36 0 0,1 86,50" fill="none" stroke="#e5e7eb" strokeWidth={8} strokeLinecap="round" />
        <path d={`M14,50 A36,36 0 0,1 ${x},${y}`} fill="none" stroke={color} strokeWidth={8} strokeLinecap="round" />
        <line x1={cx} y1={cy} x2={x} y2={y} stroke="#374151" strokeWidth={2} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={3} fill="#374151" />
      </svg>
      <div className="text-center -mt-1">
        <p className="text-sm font-bold" style={{ color }}>{value.toFixed(2)}</p>
        <p className="text-xs text-gray-500">{label}</p>
      </div>
    </div>
  );
}

// ── Supervisor Chat ───────────────────────────────────────────────────────────
function SupervisorTab() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "hydra",
      text: "Hi! I'm Nifty Node Bot. I can forecast where a stock price might go, find two stocks that move together, test trading strategies on past data, and measure your portfolio risk. What would you like to explore?",
      time: new Date().toLocaleTimeString(),
    }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const SUGGESTIONS = [
    "Forecast RELIANCE for 5 days",
    "Analyze pair HDFCBANK and ICICIBANK",
    "What is the VaR of TCS INFY WIPRO?",
    "Backtest ONGC BPCL pair",
    "Sentiment for TATAMOTORS",
  ];

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function send(text?: string) {
    const q = (text || input).trim();
    if (!q) return;
    setInput("");
    setMessages(m => [...m, { role: "user", text: q, time: new Date().toLocaleTimeString() }]);
    setLoading(true);
    try {
      const d = await hPost("/hydra/query", { query: q });
      // plain_english is the human-readable explanation; fall back to summary, then error
      const displayText = d.plain_english || d.summary || d.error || "Done — see details below.";
      setMessages(m => [...m, {
        role: "hydra",
        text: displayText,
        data: d,
        time: new Date().toLocaleTimeString(),
      }]);
    } catch {
      setMessages(m => [...m, { role: "hydra", text: "Something went wrong — please try again.", time: new Date().toLocaleTimeString() }]);
    } finally {
      setLoading(false);
    }
  }

  function renderData(d: any) {
    if (!d || d.error) return null;
    const intent = d.intent;

    if (intent === "forecast" && d.result?.p50) {
      const r = d.result;
      return (
        <div className="mt-2 bg-white border border-indigo-100 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-600">{r.symbol} — {r.horizonDays}d Forecast</span>
            <SignalBadge signal={r.direction} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            {["p10", "p50", "p90"].map(k => (
              <div key={k} className="bg-gray-50 rounded p-2">
                <p className="text-xs text-gray-500">{k.toUpperCase()}</p>
                <p className="font-bold text-sm">₹{r[k]?.[r[k].length - 1]?.toFixed(1)}</p>
              </div>
            ))}
          </div>
          <div className="text-xs text-gray-500">
            RSI {r.rsi} · Vol {r.dailyVolPct}%/day · {r.modelType?.split("(")[0]}
          </div>
        </div>
      );
    }
    if (intent === "pairs" && d.result?.ou) {
      const r = d.result;
      return (
        <div className="mt-2 bg-white border border-purple-100 rounded-lg p-3 space-y-1">
          <div className="flex justify-between items-center">
            <span className="text-xs font-semibold">{r.symbolA} / {r.symbolB}</span>
            <SignalBadge signal={r.signal?.signal || "HOLD"} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs text-center">
            <div><p className="text-gray-500">p-value</p><p className="font-bold">{fmtN(r.cointegrationPValue, 4)}</p></div>
            <div><p className="text-gray-500">Half-life</p><p className="font-bold">{fmtN(r.ou?.halfLife, 1)}d</p></div>
            <div><p className="text-gray-500">Z-score</p><p className="font-bold">{fmtN(r.ou?.zScore, 2)}</p></div>
          </div>
          {!r.isCointegrated && <p className="text-xs text-amber-600">⚠️ {r.warning}</p>}
        </div>
      );
    }
    if (intent === "var" && d.result?.portfolioVarPct != null) {
      const r = d.result;
      return (
        <div className="mt-2 bg-white border border-red-100 rounded-lg p-3">
          <p className="text-xs font-semibold mb-2">Portfolio VaR ({(r.confidence * 100).toFixed(0)}%)</p>
          <div className="grid grid-cols-2 gap-2 text-xs text-center">
            <div className="bg-red-50 rounded p-2"><p className="text-gray-500">1-day VaR</p><p className="font-bold text-red-700">{fmtN(r.portfolioVarPct, 2)}%</p></div>
            <div className="bg-red-50 rounded p-2"><p className="text-gray-500">CVaR</p><p className="font-bold text-red-700">{fmtN(r.portfolioCvarPct, 2)}%</p></div>
          </div>
        </div>
      );
    }
    if (intent === "backtest" && d.result?.metrics) {
      const m = d.result.metrics;
      return (
        <div className="mt-2 bg-white border border-green-100 rounded-lg p-3">
          <p className="text-xs font-semibold mb-2">Backtest: {d.symbolA} / {d.symbolB}</p>
          <div className="grid grid-cols-2 gap-1 text-xs">
            <div className="bg-gray-50 rounded p-1.5 text-center"><p className="text-gray-500">Return</p><p className="font-bold">{fmt(m.totalReturnPct)}%</p></div>
            <div className="bg-gray-50 rounded p-1.5 text-center"><p className="text-gray-500">Sharpe</p><p className="font-bold">{fmtN(m.annSharpe, 2)}</p></div>
            <div className="bg-gray-50 rounded p-1.5 text-center"><p className="text-gray-500">Max DD</p><p className="font-bold text-red-600">-{fmtN(m.maxDrawdownPct, 1)}%</p></div>
            <div className="bg-gray-50 rounded p-1.5 text-center"><p className="text-gray-500">Win Rate</p><p className="font-bold">{fmtN(m.winRatePct, 1)}%</p></div>
          </div>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            {m.role === "hydra" && (
              <img src="/niftynodes-logo.png" alt="" className="w-7 h-7 rounded-full object-cover flex-shrink-0 self-start mt-1 mr-2" />
            )}
            <div className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 ${m.role === "user"
              ? "bg-indigo-600 text-white rounded-br-none"
              : "bg-gray-100 text-gray-800 rounded-bl-none"
            }`}>
              <p className="text-sm leading-relaxed whitespace-pre-line">
                {m.text.split(/(\*\*[^*]+\*\*)/).map((part, pi) =>
                  part.startsWith("**") && part.endsWith("**")
                    ? <strong key={pi}>{part.slice(2, -2)}</strong>
                    : part
                )}
              </p>
              {m.data && renderData(m.data)}
              <p className={`text-[10px] mt-1 ${m.role === "user" ? "text-indigo-200 text-right" : "text-gray-400"}`}>{m.time}</p>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start items-end gap-2">
            <img src="/niftynodes-logo.png" alt="" className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
            <div className="bg-gray-100 rounded-2xl rounded-bl-none px-4 py-3">
              <div className="flex gap-1 items-center">
                {[0, 1, 2].map(i => (
                  <span key={i} className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      <div className="px-3 pt-1 flex gap-1.5 overflow-x-auto pb-1 flex-shrink-0">
        {SUGGESTIONS.map(s => (
          <button key={s} onClick={() => send(s)} disabled={loading}
            className="text-xs px-3 py-1.5 rounded-full border border-indigo-200 bg-white text-indigo-600 hover:bg-indigo-50 whitespace-nowrap transition disabled:opacity-50 flex-shrink-0">
            {s}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="px-3 py-2.5 border-t border-gray-100 flex-shrink-0">
        <div className="flex gap-2 items-center bg-gray-100 rounded-xl px-3 py-1.5">
          <input
            className="flex-1 bg-transparent text-sm focus:outline-none placeholder:text-gray-400"
            placeholder="Ask anything — forecast, pairs, risk, sentiment..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
            disabled={loading}
          />
          <button onClick={() => send()} disabled={loading || !input.trim()}
            className="px-4 py-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition">
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Pairs Trading Tab ─────────────────────────────────────────────────────────
function PairsTab() {
  const [symA, setSymA] = useState("RELIANCE");
  const [symB, setSymB] = useState("ONGC");
  const [result, setResult] = useState<any>(null);
  const [scanResult, setScanResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanSyms, setScanSyms] = useState("RELIANCE,ONGC,BPCL,HDFCBANK,ICICIBANK,KOTAKBANK,TCS,INFY,WIPRO,HCLTECH");

  async function analyze() {
    setLoading(true); setResult(null);
    try {
      setResult(await hPost("/hydra/pairs/analyze", { symbolA: symA, symbolB: symB }));
    } catch { setResult({ error: "Request failed" }); }
    finally { setLoading(false); }
  }

  async function scan() {
    setScanLoading(true); setScanResult(null);
    const syms = scanSyms.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
    try {
      setScanResult(await hPost("/hydra/pairs/scan", { symbols: syms }));
    } catch { setScanResult({ error: "Scan failed" }); }
    finally { setScanLoading(false); }
  }

  const ou = result?.ou;
  const sig = result?.signal;
  const zScore = ou?.zScore ?? 0;

  return (
    <div className="space-y-5">
      {/* Pair analyzer */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
          <Target className="w-4 h-4 text-purple-600" /> Stock Pair Analyzer
        </h3>
        <div className="flex flex-wrap gap-2 items-end">
          <div>
            <label className="text-xs text-gray-500">Stock A (NSE symbol)</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-32 uppercase focus:ring-2 focus:ring-purple-400 focus:outline-none"
              value={symA} onChange={e => setSymA(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Stock B (NSE symbol)</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-32 uppercase focus:ring-2 focus:ring-purple-400 focus:outline-none"
              value={symB} onChange={e => setSymB(e.target.value.toUpperCase())} />
          </div>
          <button onClick={analyze} disabled={loading}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition flex items-center gap-2">
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Analyze Pair
          </button>
        </div>

        {result?.error && <p className="text-red-600 text-sm mt-3">{result.error}</p>}

        {result && !result.error && (
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric label="Pair Match Score" value={fmtN(result.cointegrationPValue, 4)}
                sub={result.isCointegrated ? "✅ Good pair — they move together" : "⚠️ These stocks don't reliably move together"} color={result.isCointegrated ? "text-green-700" : "text-amber-600"} />
              <Metric label="Position Ratio" value={fmtN(result.hedgeRatio, 4)} sub="How much of Stock B per Stock A" />
              <Metric label="Correlation" value={fmtN(result.correlation, 3)} sub="How closely they move together (1 = identical)" />
              <Metric label="Recovery Time" value={`${fmtN(ou?.halfLife, 1)}d`} sub="Days until prices realign after diverging" />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric label="Average Gap" value={fmtN(ou?.mu, 4)} sub="Normal price difference between the two stocks" />
              <Metric label="Pull-Back Speed" value={fmtN(ou?.theta, 4)} sub="How quickly prices snap back to normal" />
              <Metric label="Gap Volatility" value={fmtN(ou?.sigma, 4)} sub="Typical day-to-day gap swings" />
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500 mb-1">Gap Score (how far from normal)</p>
                <Gauge value={zScore} min={-4} max={4} label={`${fmtN(zScore, 2)}σ`} />
              </div>
            </div>

            {sig && (
              <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-indigo-800">Trading Signal</span>
                  <SignalBadge signal={sig.signal} />
                </div>
                <p className="text-sm text-indigo-700">{sig.rationale}</p>
                <div className="mt-2 flex gap-4 text-xs text-indigo-600">
                  <span>Entry: ±{sig.entryThreshold}σ</span>
                  <span>Exit: ±{sig.exitThreshold}σ</span>
                  {sig.strength > 0 && <span>Confidence: {sig.strength}%</span>}
                </div>
              </div>
            )}

            {result.spreadSeries?.length > 1 && (
              <div>
                <p className="text-xs text-gray-500 mb-2">Spread (A − β·B) — last 60 days</p>
                <div className="bg-gray-50 rounded-lg p-3">
                  <Sparkline data={result.spreadSeries} color="#7c3aed" width={500} height={60} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Pair Scanner */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-600" /> Cointegrated Pair Scanner (Bonferroni corrected)
        </h3>
        <div className="flex gap-2 items-end flex-wrap">
          <div className="flex-1 min-w-[240px]">
            <label className="text-xs text-gray-500">Symbols (comma-separated)</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-full focus:ring-2 focus:ring-amber-400 focus:outline-none"
              value={scanSyms} onChange={e => setScanSyms(e.target.value)} />
          </div>
          <button onClick={scan} disabled={scanLoading}
            className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 disabled:opacity-50 transition flex items-center gap-2">
            {scanLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Scan Pairs
          </button>
        </div>

        {scanResult?.pairs && (
          <div className="mt-4">
            <p className="text-xs text-gray-500 mb-2">{scanResult.totalFound} cointegrated pairs found</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 border-b">
                    <th className="text-left pb-2">Pair</th>
                    <th className="text-right pb-2">p-value</th>
                    <th className="text-right pb-2">Bonferroni</th>
                    <th className="text-right pb-2">Z-score</th>
                    <th className="text-right pb-2">Half-life</th>
                    <th className="text-right pb-2">Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {scanResult.pairs.map((p: any, i: number) => (
                    <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="py-2 font-medium">{p.symbolA} / {p.symbolB}</td>
                      <td className="text-right">{fmtN(p.pValue, 4)}</td>
                      <td className="text-right">{p.passedBonferroni
                        ? <CheckCircle2 className="w-4 h-4 text-green-500 inline" />
                        : <XCircle className="w-4 h-4 text-gray-300 inline" />}</td>
                      <td className="text-right">{fmtN(p.zScore, 2)}σ</td>
                      <td className="text-right">{fmtN(p.halfLife, 1)}d</td>
                      <td className="text-right"><SignalBadge signal={p.signal} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Backtest Tab ──────────────────────────────────────────────────────────────
function BacktestTab() {
  const [symA, setSymA] = useState("HDFCBANK");
  const [symB, setSymB] = useState("ICICIBANK");
  const [entryZ, setEntryZ] = useState("2.0");
  const [exitZ, setExitZ] = useState("0.5");
  const [capital, setCapital] = useState("1000000");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true); setResult(null);
    try {
      setResult(await hPost("/hydra/backtest", {
        symbolA: symA, symbolB: symB,
        entryZ: parseFloat(entryZ), exitZ: parseFloat(exitZ),
        initialCapital: parseFloat(capital),
      }));
    } catch { setResult({ error: "Backtest failed" }); }
    finally { setLoading(false); }
  }

  const m = result?.metrics;
  const equity = result?.equityCurve;

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Play className="w-4 h-4 text-green-600" /> Historical Strategy Test
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
          {[["Stock A", symA, setSymA], ["Stock B", symB, setSymB],
            ["Starting Capital (₹)", capital, setCapital],
            ["Entry Gap (how wide before trading)", entryZ, setEntryZ], ["Exit Gap (how close before closing)", exitZ, setExitZ]
          ].map(([label, val, setter]: any) => (
            <div key={label}>
              <label className="text-xs text-gray-500">{label}</label>
              <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-full focus:ring-2 focus:ring-green-400 focus:outline-none uppercase"
                value={val} onChange={e => setter(e.target.value)} />
            </div>
          ))}
        </div>
        <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 mb-4 text-xs text-blue-700">
          <Info className="w-3 h-3 inline mr-1" />
          Tests the strategy on real past prices, simulating actual trade costs (₹20/trade + 0.05% slippage). Results show exactly how the strategy would have performed.
        </div>
        <button onClick={run} disabled={loading}
          className="px-5 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 transition flex items-center gap-2">
          {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {loading ? "Running backtest…" : "Run Backtest"}
        </button>
      </div>

      {result?.error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{result.error}</div>
      )}

      {m && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label="Total Profit / Loss" value={`${fmt(m.totalReturnPct)}%`}
              color={m.totalReturnPct >= 0 ? "text-green-700" : "text-red-700"} icon={<TrendingUp className="w-4 h-4" />} />
            <MetricCard label="Risk-Adjusted Return" value={fmtN(m.annSharpe, 2)}
              color={m.annSharpe >= 1 ? "text-green-700" : m.annSharpe >= 0 ? "text-amber-600" : "text-red-700"} icon={<Activity className="w-4 h-4" />} />
            <MetricCard label="Biggest Loss Period" value={`-${fmtN(m.maxDrawdownPct, 1)}%`} color="text-red-600" icon={<TrendingDown className="w-4 h-4" />} />
            <MetricCard label="Winning Trades" value={`${fmtN(m.winRatePct, 1)}%`}
              color={m.winRatePct >= 50 ? "text-green-700" : "text-red-700"} icon={<Target className="w-4 h-4" />} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Metric label="No. of Trades" value={m.totalTrades} />
            <Metric label="Starting Amount" value={fmtINR(m.initialEquity)} />
            <Metric label="Ending Value" value={fmtINR(m.finalEquity)} />
            <Metric label="Days Tested" value={result.totalDays} />
          </div>

          {equity?.length > 2 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 mb-2">Portfolio Growth Chart</p>
              <Sparkline data={equity}
                color={m.totalReturnPct >= 0 ? "#16a34a" : "#dc2626"}
                width={Math.min(700, window.innerWidth - 100)}
                height={80} />
            </div>
          )}

          {result.trades?.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs font-semibold text-gray-700 mb-2">Recent Trades</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b">
                      <th className="text-left pb-1">Symbol</th>
                      <th className="text-right pb-1">Date</th>
                      <th className="text-right pb-1">Exit Price</th>
                      <th className="text-right pb-1">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.slice(-10).reverse().map((t: any, i: number) => (
                      <tr key={i} className="border-b border-gray-50">
                        <td className="py-1">{t.symbol}</td>
                        <td className="text-right">{t.date}</td>
                        <td className="text-right">₹{fmtN(t.exitPrice, 2)}</td>
                        <td className={`text-right font-medium ${t.pnl >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {t.pnl >= 0 ? "+" : ""}₹{t.pnl?.toLocaleString("en-IN")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── VaR Tab ───────────────────────────────────────────────────────────────────
function VaRTab() {
  const [symbols, setSymbols] = useState("RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK");
  const [confidence, setConfidence] = useState("0.95");
  const [horizon, setHorizon] = useState("1");
  const [portVal, setPortVal] = useState("1000000");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function calculate() {
    setLoading(true); setResult(null);
    const syms = symbols.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
    try {
      setResult(await hPost("/hydra/var", {
        symbols: syms, confidence: parseFloat(confidence),
        horizon: parseInt(horizon), portfolioValue: parseFloat(portVal),
      }));
    } catch { setResult({ error: "VaR calculation failed" }); }
    finally { setLoading(false); }
  }

  const r = result;
  const dist = r?.returnDistribution;

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Shield className="w-4 h-4 text-red-600" /> Portfolio Risk Calculator
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div className="col-span-2 md:col-span-4">
            <label className="text-xs text-gray-500">Stocks to include (comma-separated NSE symbols)</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-full focus:ring-2 focus:ring-red-400 focus:outline-none uppercase"
              value={symbols} onChange={e => setSymbols(e.target.value)} />
          </div>
          {[
            ["Confidence Level (0.95 = 95%)", confidence, setConfidence, "e.g. 0.95"],
            ["Days Ahead", horizon, setHorizon, "1, 5, 10…"],
            ["Total Investment (₹)", portVal, setPortVal, "e.g. 1000000"],
          ].map(([label, val, setter, placeholder]: any) => (
            <div key={label}>
              <label className="text-xs text-gray-500">{label}</label>
              <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-full focus:ring-2 focus:ring-red-400 focus:outline-none"
                value={val} onChange={e => setter(e.target.value)} placeholder={placeholder} />
            </div>
          ))}
        </div>
        <div className="bg-red-50 border border-red-100 rounded-lg p-3 mb-4 text-xs text-red-700">
          <AlertTriangle className="w-3 h-3 inline mr-1" />
          Based on real historical price data — shows the worst losses that actually happened, not just theoretical ones.
        </div>
        <button onClick={calculate} disabled={loading}
          className="px-5 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 disabled:opacity-50 transition flex items-center gap-2">
          {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
          Calculate VaR
        </button>
      </div>

      {r?.error && <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{r.error}</div>}

      {r && !r.error && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label={`Worst-Case Daily Loss (${(r.confidence * 100).toFixed(0)}%)`}
              value={`${fmtN(r.portfolioVarPct, 2)}%`} color="text-red-700" icon={<Shield className="w-4 h-4" />} />
            <MetricCard label="Average Loss on Bad Days"
              value={`${fmtN(r.portfolioCvarPct, 2)}%`} color="text-red-800" icon={<AlertTriangle className="w-4 h-4" />} />
            <MetricCard label="Max Loss in Rupees (₹)"
              value={fmtINR(r.portfolioVarAbs)} color="text-orange-700" icon={<TrendingDown className="w-4 h-4" />} />
            <MetricCard label="Annual Price Swings"
              value={`${fmtN(r.portfolioVolatility, 2)}%`} color="text-amber-700" icon={<Activity className="w-4 h-4" />} />
          </div>

          {dist && (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <p className="text-sm font-semibold text-gray-700 mb-3">Daily Return Range (Historical)</p>
              <div className="flex items-end gap-2 h-20">
                {Object.entries(dist).map(([k, v]: any) => {
                  const pct = Math.max(5, Math.min(95, 50 + v * 500));
                  const isNeg = v < 0;
                  return (
                    <div key={k} className="flex-1 flex flex-col items-center gap-1">
                      <div className="w-full rounded-t" style={{
                        height: `${pct}%`,
                        backgroundColor: isNeg ? "#ef4444" : "#22c55e",
                        opacity: 0.6 + Math.abs(v) * 10,
                      }} />
                      <span className="text-xs text-gray-600 font-medium">{(v * 100).toFixed(2)}%</span>
                      <span className="text-xs text-gray-400">{k}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {r.breakdown?.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <p className="text-sm font-semibold text-gray-700 mb-3">Risk per Stock</p>
              <div className="space-y-2">
                {r.breakdown.map((b: any) => (
                  <div key={b.symbol} className="flex items-center gap-3">
                    <span className="text-sm font-medium w-24">{b.symbol}</span>
                    <span className="text-xs text-gray-500 w-16">{(b.weight * 100).toFixed(0)}% weight</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-2">
                      <div className="bg-red-500 h-2 rounded-full"
                        style={{ width: `${Math.min(100, Math.abs(b.varPct) * 20)}%` }} />
                    </div>
                    <span className="text-xs font-medium text-red-700 w-16 text-right">
                      VaR {fmtN(b.varPct, 2)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Forecast Tab ──────────────────────────────────────────────────────────────
function ForecastTab() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [horizon, setHorizon] = useState("5");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true); setResult(null);
    try {
      setResult(await hPost("/hydra/forecast", {
        symbol, horizon: parseInt(horizon),
      }));
    } catch { setResult({ error: "Forecast failed" }); }
    finally { setLoading(false); }
  }

  const r = result;
  const hasData = r && !r.error && r.p50?.length;

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Brain className="w-4 h-4 text-indigo-600" /> AI Price Forecast
        </h3>
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <label className="text-xs text-gray-500">Stock Symbol (e.g. RELIANCE)</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-36 uppercase focus:ring-2 focus:ring-indigo-400 focus:outline-none"
              value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Days to Forecast</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-28 focus:ring-2 focus:ring-indigo-400 focus:outline-none"
              value={horizon} onChange={e => setHorizon(e.target.value)} type="number" min={1} max={30} />
          </div>
          <button onClick={run} disabled={loading}
            className="px-5 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 transition flex items-center gap-2">
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
            {loading ? "Forecasting…" : "Generate Forecast"}
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-3">
          Uses price trends, momentum, trading volume, and market sentiment to generate three scenarios: pessimistic, most likely, and optimistic.
        </p>
      </div>

      {r?.error && <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{r.error}</div>}

      {hasData && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label="Latest Price" value={`₹${r.latestPrice?.toFixed(2)}`} icon={<BarChart3 className="w-4 h-4" />} />
            <MetricCard label={`${r.horizonDays}-Day Target Price`}
              value={`₹${r.p50?.[r.p50.length - 1]?.toFixed(2)}`} icon={<Target className="w-4 h-4" />} />
            <MetricCard label="Estimated Gain / Loss" value={`${fmt(r.expectedReturn)}%`}
              color={r.expectedReturn >= 0 ? "text-green-700" : "text-red-700"} icon={<TrendingUp className="w-4 h-4" />} />
            <MetricCard label="Direction" value={<SignalBadge signal={r.direction} />} icon={<Zap className="w-4 h-4" />} />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-sm font-semibold text-gray-700 mb-3">Price Forecast — 3 Scenarios</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 border-b">
                    <th className="text-left pb-2">Date</th>
                    <th className="text-right pb-2 text-red-600">Pessimistic</th>
                    <th className="text-right pb-2 text-indigo-600">Most Likely</th>
                    <th className="text-right pb-2 text-green-600">Optimistic</th>
                    <th className="text-right pb-2">Range</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-gray-50 bg-gray-50">
                    <td className="py-2 text-gray-500">Today ({r.latestDate})</td>
                    <td className="text-right text-gray-600">₹{r.latestPrice?.toFixed(2)}</td>
                    <td className="text-right text-gray-600 font-medium">₹{r.latestPrice?.toFixed(2)}</td>
                    <td className="text-right text-gray-600">₹{r.latestPrice?.toFixed(2)}</td>
                    <td className="text-right text-gray-400">—</td>
                  </tr>
                  {r.forecastDates?.map((date: string, i: number) => {
                    const range = r.p90[i] - r.p10[i];
                    const retPct = ((r.p50[i] - r.latestPrice) / r.latestPrice * 100);
                    return (
                      <tr key={date} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2">{date}</td>
                        <td className="text-right text-red-600">₹{r.p10[i]?.toFixed(2)}</td>
                        <td className={`text-right font-medium ${retPct >= 0 ? "text-green-700" : "text-red-700"}`}>
                          ₹{r.p50[i]?.toFixed(2)} <span className="text-xs font-normal">({fmt(retPct)}%)</span>
                        </td>
                        <td className="text-right text-green-600">₹{r.p90[i]?.toFixed(2)}</td>
                        <td className="text-right text-gray-400 text-xs">±₹{(range / 2).toFixed(2)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs font-semibold text-gray-600 mb-3">What Drives This Forecast</p>
              <div className="space-y-2">
                {Object.entries(r.featureImportance || {}).map(([k, v]: any) => (
                  <div key={k} className="flex items-center gap-2">
                    <span className="text-xs text-gray-600 w-32">{k.replace(/_/g, " ")}</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                      <div className="bg-indigo-500 h-1.5 rounded-full" style={{ width: `${Math.min(100, v)}%` }} />
                    </div>
                    <span className="text-xs text-gray-500 w-10 text-right">{v}%</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs font-semibold text-gray-600 mb-3">Technical Signals Used</p>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-gray-500">RSI (14)</span><span className="font-medium">{r.rsi}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Daily Volatility</span><span className="font-medium">{r.dailyVolPct}%</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Sentiment Score</span><span className="font-medium">{r.sentiment?.compound?.toFixed(3)}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Input Window</span><span className="font-medium">{r.inputWindow} days</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Sentiment Label</span>
                  <span className={`font-medium ${r.sentiment?.label?.includes("POS") ? "text-green-600" : r.sentiment?.label?.includes("NEG") ? "text-red-600" : "text-gray-600"}`}>
                    {r.sentiment?.label}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Reusable metric components ────────────────────────────────────────────────
function Metric({ label, value, sub, color = "text-gray-900" }: any) {
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-base font-bold mt-0.5 ${color}`}>{value ?? "—"}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function MetricCard({ label, value, color = "text-gray-800", icon }: any) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-2 text-gray-400">{icon}<p className="text-xs">{label}</p></div>
      <div className={`text-xl font-bold ${color}`}>{value}</div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: "supervisor", label: "Ask AI",   icon: Brain      },
  { id: "pairs",      label: "Pairs",    icon: Target     },
  { id: "backtest",   label: "Backtest", icon: Play       },
  { id: "var",        label: "Risk",     icon: Shield     },
  { id: "forecast",   label: "Forecast", icon: TrendingUp },
];

export default function HydraAlpha() {
  const [tab, setTab] = useState<Tab>("supervisor");
  const [status, setStatus] = useState<any>(null);

  useEffect(() => {
    hGet("/hydra/status").then(setStatus).catch(() => {});
  }, []);

  return (
    <div className="flex flex-col bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"
         style={{ height: "calc(100vh - 48px)" }}>

      {/* ── Slim header ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <img src="/niftynodes-logo.png" alt="NiftyNodes" className="w-8 h-8 rounded-full object-cover" />
          <div className="leading-tight">
            <p className="text-sm font-bold text-gray-900">Nifty Node Bot</p>
            <p className="text-[11px] text-gray-400">AI-powered stock analysis</p>
          </div>
        </div>
        {status && (
          <span className="flex items-center gap-1.5 text-[11px] text-green-700 bg-green-50 border border-green-100 px-2.5 py-1 rounded-full font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            Live
          </span>
        )}
      </div>

      {/* ── Compact tab strip ─────────────────────────────────────────── */}
      <div className="flex border-b border-gray-100 flex-shrink-0">
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex-1 flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition-colors border-b-2 ${
                active
                  ? "border-indigo-600 text-indigo-700 bg-indigo-50/60"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50"
              }`}>
              <Icon className={`w-4 h-4 ${active ? "text-indigo-600" : "text-gray-400"}`} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* ── Tab content fills remaining height ───────────────────────── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === "supervisor" && <SupervisorTab />}
        {tab === "pairs"      && <div className="h-full overflow-y-auto p-4"><PairsTab /></div>}
        {tab === "backtest"   && <div className="h-full overflow-y-auto p-4"><BacktestTab /></div>}
        {tab === "var"        && <div className="h-full overflow-y-auto p-4"><VaRTab /></div>}
        {tab === "forecast"   && <div className="h-full overflow-y-auto p-4"><ForecastTab /></div>}
      </div>
    </div>
  );
}
