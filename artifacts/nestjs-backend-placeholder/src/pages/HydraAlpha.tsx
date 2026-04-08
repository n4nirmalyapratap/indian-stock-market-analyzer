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
  const v = Math.abs(Number(n));
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)}L`;
  return `₹${v.toLocaleString("en-IN")}`;
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
      text: "Hydra-Alpha Engine online. I can forecast stock prices, discover cointegrated pairs, run backtests, calculate Value at Risk, and analyze sentiment. What would you like to analyze?",
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
      const summary = d.summary || d.error || JSON.stringify(d).slice(0, 200);
      setMessages(m => [...m, {
        role: "hydra",
        text: summary,
        data: d,
        time: new Date().toLocaleTimeString(),
      }]);
    } catch {
      setMessages(m => [...m, { role: "hydra", text: "Engine error — please try again.", time: new Date().toLocaleTimeString() }]);
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
    <div className="flex flex-col h-[calc(100vh-180px)] min-h-[500px]">
      <div className="flex-1 overflow-y-auto space-y-3 p-2">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 ${m.role === "user"
              ? "bg-indigo-600 text-white rounded-br-sm"
              : "bg-white border border-gray-200 text-gray-800 rounded-bl-sm shadow-sm"
            }`}>
              {m.role === "hydra" && (
                <div className="flex items-center gap-1.5 mb-1">
                  <Brain className="w-3 h-3 text-indigo-600" />
                  <span className="text-xs font-semibold text-indigo-600">Hydra-Alpha Engine</span>
                  <span className="text-xs text-gray-400">{m.time}</span>
                </div>
              )}
              <p className="text-sm leading-relaxed">{m.text}</p>
              {m.data && renderData(m.data)}
              {m.role === "user" && <p className="text-xs text-indigo-200 mt-1 text-right">{m.time}</p>}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
              <div className="flex items-center gap-2">
                <Brain className="w-3 h-3 text-indigo-600 animate-pulse" />
                <span className="text-xs text-gray-500">Hydra Engine processing</span>
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <span key={i} className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce"
                      style={{ animationDelay: `${i * 0.2}s` }} />
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3 space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTIONS.map(s => (
            <button key={s} onClick={() => send(s)} disabled={loading}
              className="text-xs px-2.5 py-1 rounded-full border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition disabled:opacity-50">
              {s}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
            placeholder="Ask Hydra anything — forecast, pairs, VaR, backtest, sentiment..."
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
          <Target className="w-4 h-4 text-purple-600" /> Cointegration Analyzer (Engle-Granger)
        </h3>
        <div className="flex flex-wrap gap-2 items-end">
          <div>
            <label className="text-xs text-gray-500">Symbol A</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-32 uppercase focus:ring-2 focus:ring-purple-400 focus:outline-none"
              value={symA} onChange={e => setSymA(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Symbol B</label>
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
              <Metric label="p-value (EG test)" value={fmtN(result.cointegrationPValue, 4)}
                sub={result.isCointegrated ? "✅ Cointegrated (p<0.05)" : "⚠️ Not cointegrated"} color={result.isCointegrated ? "text-green-700" : "text-amber-600"} />
              <Metric label="Hedge Ratio (β)" value={fmtN(result.hedgeRatio, 4)} sub="OLS regression" />
              <Metric label="Correlation" value={fmtN(result.correlation, 3)} sub="Pearson r" />
              <Metric label="Half-Life" value={`${fmtN(ou?.halfLife, 1)}d`} sub="Mean reversion time" />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric label="OU Mean (μ)" value={fmtN(ou?.mu, 4)} sub="Long-run equilibrium" />
              <Metric label="OU Speed (θ)" value={fmtN(ou?.theta, 4)} sub="Reversion speed" />
              <Metric label="OU Volatility (σ)" value={fmtN(ou?.sigma, 4)} sub="Spread volatility" />
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500 mb-1">Z-Score</p>
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
          <Play className="w-4 h-4 text-green-600" /> Event-Driven Pairs Backtest
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
          {[["Symbol A", symA, setSymA], ["Symbol B", symB, setSymB],
            ["Capital (₹)", capital, setCapital],
            ["Entry Z-score", entryZ, setEntryZ], ["Exit Z-score", exitZ, setExitZ]
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
          Event-driven engine with realistic slippage (5bps) and ₹20/trade commission. 
          Processes data chronologically — no lookahead bias.
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
            <MetricCard label="Total Return" value={`${fmt(m.totalReturnPct)}%`}
              color={m.totalReturnPct >= 0 ? "text-green-700" : "text-red-700"} icon={<TrendingUp className="w-4 h-4" />} />
            <MetricCard label="Ann. Sharpe" value={fmtN(m.annSharpe, 2)}
              color={m.annSharpe >= 1 ? "text-green-700" : m.annSharpe >= 0 ? "text-amber-600" : "text-red-700"} icon={<Activity className="w-4 h-4" />} />
            <MetricCard label="Max Drawdown" value={`-${fmtN(m.maxDrawdownPct, 1)}%`} color="text-red-600" icon={<TrendingDown className="w-4 h-4" />} />
            <MetricCard label="Win Rate" value={`${fmtN(m.winRatePct, 1)}%`}
              color={m.winRatePct >= 50 ? "text-green-700" : "text-red-700"} icon={<Target className="w-4 h-4" />} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Metric label="Total Trades" value={m.totalTrades} />
            <Metric label="Initial Capital" value={fmtINR(m.initialEquity)} />
            <Metric label="Final Equity" value={fmtINR(m.finalEquity)} />
            <Metric label="Trading Days" value={result.totalDays} />
          </div>

          {equity?.length > 2 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 mb-2">Equity Curve</p>
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
          <Shield className="w-4 h-4 text-red-600" /> Historical Simulation VaR
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div className="col-span-2 md:col-span-4">
            <label className="text-xs text-gray-500">Symbols (comma-separated, equal weight)</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-full focus:ring-2 focus:ring-red-400 focus:outline-none uppercase"
              value={symbols} onChange={e => setSymbols(e.target.value)} />
          </div>
          {[
            ["Confidence", confidence, setConfidence, "e.g. 0.95"],
            ["Horizon (days)", horizon, setHorizon, "1, 5, 10…"],
            ["Portfolio Value (₹)", portVal, setPortVal, "e.g. 1000000"],
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
          Non-parametric historical simulation — captures fat tails. No normal distribution assumption.
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
            <MetricCard label={`${(r.confidence * 100).toFixed(0)}% VaR`}
              value={`${fmtN(r.portfolioVarPct, 2)}%`} color="text-red-700" icon={<Shield className="w-4 h-4" />} />
            <MetricCard label="CVaR (Expected Shortfall)"
              value={`${fmtN(r.portfolioCvarPct, 2)}%`} color="text-red-800" icon={<AlertTriangle className="w-4 h-4" />} />
            <MetricCard label="VaR (₹)"
              value={fmtINR(r.portfolioVarAbs)} color="text-orange-700" icon={<TrendingDown className="w-4 h-4" />} />
            <MetricCard label="Ann. Volatility"
              value={`${fmtN(r.portfolioVolatility, 2)}%`} color="text-amber-700" icon={<Activity className="w-4 h-4" />} />
          </div>

          {dist && (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <p className="text-sm font-semibold text-gray-700 mb-3">Return Distribution (Percentiles)</p>
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
              <p className="text-sm font-semibold text-gray-700 mb-3">Individual Risk Breakdown</p>
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
          <Brain className="w-4 h-4 text-indigo-600" /> TFT-Inspired Probabilistic Forecast
        </h3>
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <label className="text-xs text-gray-500">Symbol</label>
            <input className="block mt-1 px-3 py-2 border border-gray-200 rounded-lg text-sm w-36 uppercase focus:ring-2 focus:ring-indigo-400 focus:outline-none"
              value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Horizon (days)</label>
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
          Features: OHLCV · RSI · MACD · Bollinger · Momentum (5/20d) · Volume Z-score · VADER Sentiment.
          Ensemble: EWM + Momentum + Mean-Reversion, dynamically weighted by RSI context.
        </p>
      </div>

      {r?.error && <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{r.error}</div>}

      {hasData && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label="Latest Price" value={`₹${r.latestPrice?.toFixed(2)}`} icon={<BarChart3 className="w-4 h-4" />} />
            <MetricCard label={`${r.horizonDays}d P50 (Base)`}
              value={`₹${r.p50?.[r.p50.length - 1]?.toFixed(2)}`} icon={<Target className="w-4 h-4" />} />
            <MetricCard label="Expected Return" value={`${fmt(r.expectedReturn)}%`}
              color={r.expectedReturn >= 0 ? "text-green-700" : "text-red-700"} icon={<TrendingUp className="w-4 h-4" />} />
            <MetricCard label="Direction" value={<SignalBadge signal={r.direction} />} icon={<Zap className="w-4 h-4" />} />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-sm font-semibold text-gray-700 mb-3">Probabilistic Price Path</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 border-b">
                    <th className="text-left pb-2">Date</th>
                    <th className="text-right pb-2 text-red-600">P10 (Bear)</th>
                    <th className="text-right pb-2 text-indigo-600">P50 (Base)</th>
                    <th className="text-right pb-2 text-green-600">P90 (Bull)</th>
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
              <p className="text-xs font-semibold text-gray-600 mb-3">Feature Importance</p>
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
              <p className="text-xs font-semibold text-gray-600 mb-3">Model Indicators</p>
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
const TABS: { id: Tab; label: string; icon: any; description: string }[] = [
  { id: "supervisor", label: "Supervisor",  icon: Brain,    description: "Natural language query router" },
  { id: "pairs",      label: "Pairs Trader",icon: Target,   description: "Cointegration + OU signals" },
  { id: "backtest",   label: "Backtest",    icon: Play,     description: "Event-driven engine" },
  { id: "var",        label: "Risk / VaR",  icon: Shield,   description: "Historical simulation" },
  { id: "forecast",   label: "Forecast",    icon: TrendingUp, description: "TFT-inspired P10/P50/P90" },
];

export default function HydraAlpha() {
  const [tab, setTab] = useState<Tab>("supervisor");
  const [status, setStatus] = useState<any>(null);

  useEffect(() => {
    hGet("/hydra/status").then(setStatus).catch(() => {});
  }, []);

  return (
    <div className="space-y-5 max-w-5xl mx-auto">
      {/* Header */}
      <div className="bg-gradient-to-br from-indigo-900 via-purple-900 to-indigo-800 rounded-2xl p-6 text-white">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center">
                <Brain className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold">Hydra-Alpha Engine</h1>
                <p className="text-indigo-300 text-sm">BlackRock Aladdin-Inspired Quantitative Analysis Platform</p>
              </div>
            </div>
            <p className="text-indigo-200 text-sm mt-2 max-w-2xl">
              Multi-module federated architecture: Supervisor Agent → Expert Agents (Pairs Trader, 
              Event-Driven Backtester, Historical VaR, TFT Forecaster, VADER Sentiment). 
              Powered by Engle-Granger cointegration, Ornstein-Uhlenbeck process, and statistical ensemble forecasting.
            </p>
          </div>
          {status && (
            <div className="text-right flex-shrink-0">
              <span className="inline-flex items-center gap-1.5 text-xs bg-green-500/20 text-green-300 px-2.5 py-1 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                {status.status}
              </span>
              {status.database && (
                <p className="text-xs text-indigo-400 mt-1">
                  <Database className="w-3 h-3 inline mr-1" />
                  {status.database.totalRows?.toLocaleString() || 0} price rows cached
                </p>
              )}
            </div>
          )}
        </div>

        {/* Module pills */}
        <div className="flex flex-wrap gap-2 mt-4">
          {["OHLCV DB", "VADER NLP", "Engle-Granger", "OU Process", "Event-Driven BT", "Hist. VaR", "TFT Ensemble"].map(m => (
            <span key={m} className="text-xs bg-white/10 text-indigo-200 px-2.5 py-0.5 rounded-full">{m}</span>
          ))}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl overflow-x-auto">
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition flex-shrink-0 ${
                active ? "bg-white text-indigo-700 shadow-sm" : "text-gray-600 hover:text-gray-900"
              }`}>
              <Icon className={`w-4 h-4 ${active ? "text-indigo-600" : "text-gray-400"}`} />
              <div className="text-left">
                <div>{t.label}</div>
                {active && <div className="text-xs font-normal text-indigo-400 hidden md:block">{t.description}</div>}
              </div>
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div>
        {tab === "supervisor" && <SupervisorTab />}
        {tab === "pairs"      && <PairsTab />}
        {tab === "backtest"   && <BacktestTab />}
        {tab === "var"        && <VaRTab />}
        {tab === "forecast"   && <ForecastTab />}
      </div>
    </div>
  );
}
