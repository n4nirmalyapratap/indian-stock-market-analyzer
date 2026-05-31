import React, { useState, useRef, useEffect } from "react";
import { useLocation } from "wouter";
import { BookOpen, Send, X, RotateCcw, Sparkles, ChevronRight, ChevronLeft, GraduationCap, Bot } from "lucide-react";
import { fetchApi } from "@/lib/api";

// ── Options AI chat helper ────────────────────────────────────────────────────
async function optionsChat(messages: { role: string; content: string }[]): Promise<string> {
  const d = await fetchApi<{ reply?: string }>("/options/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  return d.reply ?? "Sorry, I couldn't get a response.";
}

// ── Smart fallback — when KB doesn't match, ask the backend assistant
async function smartFallback(question: string): Promise<string | null> {
  try {
    const d = await fetchApi<{ reply?: string }>("/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });
    const reply = (d.reply || "").trim();
    return reply || null;
  } catch {
    return null;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Knowledge base — market concepts + every app feature, in plain English
// ─────────────────────────────────────────────────────────────────────────────
interface Entry {
  id: string;
  title: string;
  keywords: string[];
  answer: string;
  related?: string[];  // ids of related entries
}

const KB: Entry[] = [
  // ── App Overview ──────────────────────────────────────────────────────────
  {
    id: "app-overview",
    title: "What is this app?",
    keywords: ["app", "this app", "what is", "nifty node", "platform", "overview", "about"],
    answer: `This is **Nifty Node** — an Indian Stock Market Analysis Platform.

It gives you real-time tools to understand what's happening in the NSE (National Stock Exchange) market, all in one place:

🗂️ **Dashboard** — quick snapshot of the whole market
📊 **Chart Studio** — live interactive charts for any stock
🏭 **Market Sectors** — see which sectors are up or down
🔍 **Stock Lookup** — deep dive into any NSE stock
🕯️ **Patterns** — automatically detected candlestick patterns
🔎 **Scanners** — filter stocks by technical criteria
🤖 **AI Stock Analyst** — get a full AI-written report on any stock
🧑‍⚖️ **Investor Council** — see how 8 different investor personas rate a stock
💼 **Portfolio** — track your holdings, see gains, generate tax reports
📐 **Options Tester** — build and test options strategies
🌏 **Insights** — IPOs, FII/DII flows, macro pulse, bulk deals
📰 **News & Sentiment** — live market news with sentiment scoring
📩 **Daily Digest** — get a portfolio summary on email every morning
💬 **Telegram & WhatsApp bots** — ask the market anything from your phone

Everything connects to live NSE/BSE data. Sign in with Google to start.`,
    related: ["dashboard", "chart-studio", "sectors-page", "stock-lookup", "patterns-page", "scanners-page", "ai-stock-analyst", "investor-council", "portfolio", "options-tester", "insights-page", "telegram-bot"],
  },

  // ── App Features ─────────────────────────────────────────────────────────
  {
    id: "dashboard",
    title: "What does the Dashboard show?",
    keywords: ["dashboard", "home", "market phase", "overview", "main page", "rotation phase", "advancing", "declining", "breadth", "where to buy", "sector rotation", "macro pulse", "top movers", "global indices"],
    answer: `The **Dashboard** is your market command centre — the first thing you see when you open the app.

**What it shows (top to bottom):**

🌡️ **Macro Pulse strip** — six tile-sized readings of the Indian economy:
  • RBI Repo Rate (interest rates)
  • India CPI (inflation)
  • IIP (industrial output)
  • India 10Y G-Sec yield
  • USD/INR
  • Brent crude

📍 **Market Phase** — the overall health of the market right now:
  • *Early Bull* → market starting to rise
  • *Full Bull* → strong uptrend
  • *Late Cycle / Slowdown* → market topping out
  • *Bear Market* → market in a downtrend

📈 **Advancing / Declining** — how many sectors are going up vs down today

🎯 **Where to Buy Now** — sectors with the strongest momentum (green bars = positive, red = negative)

🚀 **Top Movers** — biggest gainers, losers, and most-active stocks across Nifty 100, Midcap, and Smallcap segments

🌏 **Global Indices** — what S&P 500, Nasdaq, Nikkei, Hang Seng, etc. did last session

🕯️ **Pattern Signals** — stocks showing bullish or bearish candlestick patterns right now

📊 **Sector Rotation Analysis** — a paragraph explaining what the market is doing and what to consider doing

**How to use it:** Check the Dashboard each morning before markets open to get a feel for the day. The Macro Pulse tells you the economic backdrop, the Market Phase tells you the trend, and "Where to Buy" shows where the action is.`,
    related: ["sector-rotation", "market-phase", "sectors-page", "macro-pulse", "fii-dii"],
  },
  {
    id: "chart-studio",
    title: "How do I use Chart Studio?",
    keywords: ["chart studio", "chart", "trading", "trading platform", "candlestick chart", "live chart", "technical analysis", "indicators"],
    answer: `**Chart Studio** is the live charting tool — think of it like a mini TradingView built into the app.

**What you can do:**

🕯️ **View candlestick charts** for any NSE stock or index (RELIANCE, TCS, NIFTY 50, etc.)

📐 **Add technical indicators:**
  • RSI — momentum oscillator
  • MACD — trend direction
  • EMA / SMA — moving averages
  • Bollinger Bands — volatility bands
  • Volume bars

🔍 **Zoom and pan** to any time period — zoom in to see individual candles, or zoom out to see the yearly trend

📊 **Multiple timeframes** — view 1-day, 1-week, or 1-month candles

**How to use it:**
1. Type a stock symbol (e.g. RELIANCE, INFY, HDFCBANK) in the search box
2. The chart loads automatically with the latest price data
3. Toggle indicators from the panel on the right
4. Use the zoom buttons or scroll to explore the chart

**Tip:** Use RSI + EMA together. If price is above the 50-EMA and RSI is between 50–70, the stock is in a healthy uptrend.`,
    related: ["rsi", "macd", "moving-averages", "candlestick"],
  },
  {
    id: "sectors-page",
    title: "What is the Market Sectors page?",
    keywords: ["sector", "sectors", "market sectors", "sector performance", "nifty it", "nifty bank", "sector page"],
    answer: `The **Market Sectors** page shows you how every major NSE sector is performing — all at once.

**What you see:**

📊 **Sector cards** — one card for each sector (IT, Banking, Pharma, Auto, FMCG, etc.) showing:
  • Today's percentage change (green = up, red = down)
  • The sector's current trend (bullish, bearish, or neutral)
  • A small sparkline showing recent price movement

🏆 **Sorted by performance** — the best-performing sector is always at the top

**Sectors covered:**
NIFTY IT · NIFTY BANK · NIFTY PHARMA · NIFTY AUTO · NIFTY FMCG · NIFTY METAL · NIFTY ENERGY · NIFTY REALTY · NIFTY HEALTHCARE · and more

**How to use it:**
Click any sector card to see all the stocks inside it and their individual performance. This helps you quickly find which stocks are moving within a strong sector.

**Key insight:** Always trade with the sector. If IT sector is up 2%, individual IT stocks are more likely to continue rising. Don't fight the sector trend.`,
    related: ["sector-rotation", "what-sector", "dashboard"],
  },
  {
    id: "stock-lookup",
    title: "How do I use Stock Lookup?",
    keywords: ["stock lookup", "lookup", "search stock", "find stock", "analyze stock", "stock detail", "stock search", "financials", "dcf", "tri factor"],
    answer: `**Stock Lookup** is the deep-dive page for any NSE-listed stock — over 500 covered across Nifty 100, Midcap 150, Smallcap 250, and the full F&O universe.

**What you get when you search a stock:**

💰 **Live price** — current price, day high/low, 52-week high/low, market cap

📊 **Technical Analysis:**
  • RSI — is it overbought or oversold?
  • MACD — what's the trend signal?
  • EMA 20 / EMA 50 / EMA 200 — is price above or below the averages?
  • Support and resistance levels
  • A Technical Summary verdict (Buy / Sell / Hold)

🎯 **Entry Signal** — a suggestion (BUY / SELL / HOLD) based on the technical indicators

📈 **Price chart** — recent price history at a glance (open it in Chart Studio for the full version)

💎 **Tri-Factor Score** — a single 0-100 score combining momentum, quality, and valuation. See the **Tri-Factor Scoring** entry for what each factor means.

🏦 **Financials tab** — revenue, profit, EPS, P/E, P/B, debt/equity, ROE, recent quarterly trends

🧮 **DCF Valuation** — a Discounted Cash Flow estimate of "fair value" with assumptions you can tweak

📰 **Latest News** — ticker-specific headlines with sentiment scores

🧑‍⚖️ **Open in Council** — see how 8 investor personas rate this stock side-by-side

🤖 **Run AI Analyst** — kick off a streaming AI report on this stock

**How to use it:**
1. Type a stock name or symbol (e.g. "Reliance", "TCS", "HDFCBANK")
2. Click Search or press Enter
3. The full analysis appears instantly
4. Scroll through the tabs — Overview, Technicals, Financials, News, etc.

**Tip:** Look for stocks where RSI is between 40–60 AND price is above the 50-day EMA AND MACD is bullish AND Tri-Factor score is above 60. That's a strong, well-rounded setup.`,
    related: ["rsi", "macd", "moving-averages", "entry-signal", "dcf-valuation", "tri-factor-scoring", "investor-council", "ai-stock-analyst"],
  },
  {
    id: "patterns-page",
    title: "What is the Patterns page?",
    keywords: ["patterns", "candlestick pattern", "pattern page", "bullish pattern", "bearish pattern", "call signal", "put signal", "hammer", "doji", "engulfing", "universe", "nifty 100", "midcap"],
    answer: `The **Patterns** page automatically scans hundreds of NSE stocks and finds candlestick patterns — visual signals that often predict the next price move.

**How it works:**
The system analyses recent candles for each stock every day. When a recognisable pattern forms, it shows up here.

**Filter by universe:**
  • **NIFTY 100** — the 100 largest stocks (most reliable signals)
  • **Midcap 150** — mid-sized stocks (more opportunities, more noise)
  • **Smallcap 250** — small stocks (high reward, high risk)

**Types of patterns:**

📗 **Bullish (CALL) patterns** — suggest the stock might go UP:
  • Hammer — buyers stepped in at the low
  • Morning Star — reversal from a downtrend
  • Bullish Engulfing — big green candle swallowing the previous red candle
  • Dragonfly Doji — long lower shadow, stock rejected lower prices

📕 **Bearish (PUT) patterns** — suggest the stock might go DOWN:
  • Shooting Star — buyers failed to hold the high
  • Evening Star — reversal from an uptrend
  • Bearish Engulfing — big red candle swallowing the previous green candle

**What each result shows:**
  • Stock symbol
  • Pattern name
  • Signal direction (CALL = possible up move, PUT = possible down move)
  • Confidence percentage — how strong the pattern is

**How to use it:** Filter by CALL or PUT. Look for high-confidence patterns (>70%) in stocks that are also in a strong sector. Then open Chart Studio to verify before making any decision.`,
    related: ["candlestick", "call-put", "chart-studio"],
  },
  {
    id: "scanners-page",
    title: "What are the Stock Scanners?",
    keywords: ["scanner", "scanners", "screener", "stock screen", "filter stocks", "golden cross", "volume spike", "momentum", "breakout", "oversold", "custom scanner", "save scanner", "ad hoc"],
    answer: `The **Scanners** page lets you filter the entire NSE market to find stocks matching specific technical criteria — automatically.

**Think of it like this:** Instead of manually checking 500 stocks, the scanner does it for you in seconds.

**Built-in scanners:**

🏆 **Golden Cross** — finds stocks where the 50-day average has crossed above the 200-day average. One of the most reliable long-term buy signals.

📊 **Momentum** — finds stocks with strong, consistent price momentum. Good for trend-following.

📈 **Volume Spike** — finds stocks where today's trading volume is much higher than usual. Big volume often signals a breakout or major event.

🎯 **Oversold Bounce** — finds stocks that have fallen a lot (RSI below 30) and might be due for a bounce upward.

📉 **Breakout** — finds stocks breaking above a key resistance level for the first time.

🐂 **Strong Trend** — stocks stacking above 20/50/200 EMAs with rising volume.

➕ **Build your own** — click "New Scanner" to create custom rules using any combination of:
  • RSI / MACD / moving average crossovers
  • Price relative to EMAs
  • Volume thresholds
  • Pattern presence
  • Market cap / sector filters

🚀 **Ad-hoc Scanner** — run a one-off custom query without saving it. Use it to experiment before committing.

💾 **Save & re-run** — every scanner you create is saved to your account. Click any saved scanner to re-run it on today's data.

**How to use it:**
1. Click any scanner card to run it
2. It scans hundreds of stocks in real time
3. Results show the matching stocks with price and percentage change
4. Click any result to open it in Stock Lookup for more detail

**Tip:** The Golden Cross scanner gives the most reliable signals. But always confirm with the Patterns page or Investor Council before acting.`,
    related: ["golden-cross", "moving-averages", "rsi", "volume", "patterns-page"],
  },
  {
    id: "ai-analyzer",
    title: "What is Hydra Alpha?",
    keywords: ["hydra", "hydra alpha", "ai analyzer", "nlp", "natural language", "ask question", "query", "supervisor"],
    answer: `**Hydra Alpha** lets you ask market questions in plain English — and get real data back instantly.

**Examples of what you can ask:**
  • "Analyze RELIANCE" → full technical analysis
  • "Which sectors are up?" → today's sector performance
  • "Show bullish patterns" → all bullish candlestick signals
  • "Where should I invest today?" → sector rotation data
  • "Run golden cross scanner" → executes the scanner
  • "Forecast TCS for 30 days" → ARIMA price forecast
  • "Find pairs to trade with HDFC" → cointegrated pair candidates
  • "Calculate VaR for my portfolio" → Value at Risk estimate

**How it works:**
A rule-based NLP engine (using spaCy under the hood) understands your question, figures out what you're asking, and routes it to the right data source. For genuinely open-ended questions, it falls back to an AI assistant.

**Best for:** Users who prefer typing questions naturally over clicking through menus. It's a fast lane to anything in the app.

**Bonus — the floating Help & Learn button (this assistant):** Click the 🎓 icon in the bottom-right of any page to ask "what is this", "how do I use that", or any beginner question about the app or markets. Different from Hydra Alpha — this one teaches; Hydra Alpha does.

**Tip:** You can combine concepts — "Show me bearish stocks in the banking sector" or "Which IT stocks are showing bullish patterns?"`,
    related: ["stock-lookup", "sectors-page", "patterns-page", "scanners-page", "ai-stock-analyst"],
  },
  {
    id: "options-tester",
    title: "What is the Options Tester?",
    keywords: ["options tester", "options", "strategy tester", "iron condor", "straddle", "strangle", "call option", "put option", "legs", "greeks", "payoff", "options strategy", "pcr", "options chain", "smart suggest"],
    answer: `The **Options Tester** is a full options strategy builder and analyser — without needing a live brokerage account.

**What you can do:**

📋 **View the live options chain** — every strike and expiry for NIFTY, BANKNIFTY, and 200+ F&O stocks, with live prices, open interest, and PCR (Put-Call Ratio)

🏗️ **Build any options strategy** by adding "legs":
  • Each leg = a call or put option, with a strike price, premium, and lots
  • Multi-leg strategies: straddles, strangles, iron condors, butterfly spreads, etc.

📐 **Analyse the strategy** to get:
  • **Payoff chart** — profit/loss at every possible price at expiry
  • **Max profit** and **max loss**
  • **Breakeven points** — where you start making or losing money
  • **Greeks** (Delta, Gamma, Theta, Vega, Rho)

⚡ **Preset strategies** — one-click load:
  Long Call, Long Put, Short Straddle, Iron Condor, Bull Call Spread, Butterfly, Calendar Spread, and more

🪄 **Smart Suggest** — describe your market view ("I think NIFTY stays flat for 2 weeks") and the tool suggests strategies that fit

🤖 **Built-in AI Chat** — the Options page has its own assistant that explains Greeks, strategies, and your specific position in plain English

🎯 **Risk Analysis tab:**
  • Value at Risk (VaR)
  • Scenario engine — how your trade performs under different price/IV shocks
  • Event-driven historical backtest — replay your strategy through past expiries

⚖️ **SEBI Compliance Check** — flags strategies that may breach current SEBI/exchange rules (lot size limits, banned strikes, etc.)

📚 **F&O Bhavcopy data** — premiums and open interest data sourced from NSE/BSE official bhavcopy files

**How to use it:**
1. Type a symbol (e.g. NIFTY, BANKNIFTY, RELIANCE) and click "Fetch Spot"
2. Add legs using a preset, Smart Suggest, or manually
3. Click "Analyse Strategy"
4. Study the payoff chart and Greeks
5. Switch to Risk tab to stress-test
6. Ask the chat assistant to explain anything`,
    related: ["call-put", "greeks", "iv", "iron-condor", "straddle"],
  },

  // ── AI Stock Analyst ──────────────────────────────────────────────────────
  {
    id: "ai-stock-analyst",
    title: "What is the AI Stock Analyst?",
    keywords: ["ai stock analyst", "ai analyst", "ai report", "deep report", "stock analysis ai", "scan", "compare", "track record"],
    answer: `The **AI Stock Analyst** writes a full research report on any NSE stock — like having an analyst on call.

**What's in a report:**

📌 **Verdict** — clear BUY / SELL / HOLD call with a confidence level
🔎 **Why** — the actual reasoning behind the call, in plain English
📊 **Technicals** — current trend, key levels, indicator readings
🏦 **Fundamentals** — revenue, profit, growth, valuation snapshot
📰 **News** — what's been happening that could move the stock
⚠️ **Risks** — what could go wrong
🎯 **Targets** — short-term and medium-term price targets

**How it works:**
Reports stream in real-time — you watch the analyst "think" through each section. Powered by an LLM (Groq for speed, OpenAI/OpenRouter as fallback), grounded in live NSE data, technicals, news, and your portfolio.

**Different modes:**

🎯 **Single ticker** → /ai-analyst/RELIANCE — deep report on one stock
🔍 **Scan mode** → /ai-analyst/scan — give it a watchlist of tickers, it analyses each one sequentially
⚖️ **Compare mode** → /ai-analyst/compare — analyses 2-5 stocks side by side, picks the best
💾 **Saved Analyses** → /ai-analyst/saved — every report you've run is saved for later
📈 **Track Record** → /ai-analyst/track-record — see how accurate the AI has been (1-day, 5-day, 30-day hit rates)

**Daily quota:**
Free users get **3 deep reports per day** (cached reports don't count against the quota — re-opening a saved report is free).

**Built-in anti-FOMO guard:**
If the AI says BUY but the stock is more than 5% above its 20-day moving average, the verdict is auto-downgraded to HOLD with a "wait for a pullback" warning. Stops you from chasing extended stocks.

**How to use it:**
1. Go to /ai-analyst or click "Run AI Analyst" from any stock page
2. Type a ticker, hit Run
3. Watch the report stream in (~30-60 seconds)
4. Save it, share it, or check the track record to see how accurate previous calls were`,
    related: ["stock-lookup", "saved-analyses", "ai-track-record", "investor-council"],
  },
  {
    id: "saved-analyses",
    title: "What are Saved Analyses?",
    keywords: ["saved analyses", "saved", "saved reports", "ai history", "my reports"],
    answer: `**Saved Analyses** is where every AI Analyst report you've run is stored.

**What you can do:**

📚 **Browse all your past reports** — sortable by date, ticker, or verdict
🔄 **Re-open any report** — cached, doesn't count against your daily quota
🗑️ **Bulk delete** — clean up old reports in one click
🔗 **Share** — copy a direct link to share with someone

**Why it matters:**
Reports are cached so re-opening "RELIANCE from last Tuesday" is free and instant. You can also build a personal track record of every call the AI made for you.

**How to use it:** Go to /ai-analyst/saved or click "My Saved" from the AI Analyst page.

**Tip:** Re-check old BUY calls a week or two later — were they right? The Track Record page does this automatically across every user's reports.`,
    related: ["ai-stock-analyst", "ai-track-record"],
  },
  {
    id: "ai-track-record",
    title: "How accurate is the AI Stock Analyst?",
    keywords: ["track record", "ai accuracy", "backtest", "hit rate", "ai performance", "is ai correct"],
    answer: `The **AI Track Record** page tells you exactly how good the AI Stock Analyst's calls have been — measured against real price moves.

**What it measures:**

For every BUY/SELL verdict the AI has ever issued:
  • Did the stock actually move the way the AI said it would?
  • At three time horizons: **1 day**, **5 days**, and **30 days** later
  • Computed automatically every night after market close

**What you'll see:**

📊 **Overall hit rate** — % of BUY calls where the stock actually rose, broken down by horizon
🎯 **By verdict** — hit rate for BUY vs SELL vs HOLD separately
📌 **By ticker** — which stocks the AI has been right (or wrong) about most often
📜 **Last 10 calls** — your most recent reports with actual outcomes

**Why this matters:**
Most AI tools claim to be accurate. This one shows you the receipts. If the AI's BUY calls only hit 45% of the time at 5-day horizon, you'll see that — and so will everyone else.

**How to use it:** Go to /ai-analyst/track-record. Use it to calibrate your trust in the AI. If a horizon shows weak accuracy, weight those calls less.`,
    related: ["ai-stock-analyst", "saved-analyses"],
  },
  {
    id: "investor-council",
    title: "What is the Investor Council?",
    keywords: ["investor council", "council", "agents", "personas", "warren buffett", "consensus", "screener consensus", "multi persona"],
    answer: `The **Investor Council** shows you how 8 different investing personalities would rate the same stock — like a panel of advisors.

**The personas:**

🧓 **Value Investor** — Buffett-style. Cares about earnings, debt, moat, fair value.
🚀 **Growth Investor** — Lynch/Cathie Wood style. Cares about revenue acceleration, TAM.
📊 **Quant** — pure numbers. Cares about Sharpe, Sortino, factor exposures.
🎯 **Technical Trader** — charts only. Cares about momentum, breakout setup.
💎 **Quality Investor** — Munger/Pabrai style. Cares about ROCE, capital efficiency.
🐢 **Dividend Investor** — yield + payout sustainability.
📰 **Macro Investor** — sees the stock through interest rates, inflation, FII flows.
🎢 **Contrarian** — buys when others are selling, asks "is this priced for disaster?"

**What you get for each stock:**

✅ **Each persona's verdict** — BUY / SELL / HOLD
💭 **Each persona's reasoning** — short paragraph in their voice and worldview
📊 **Consensus score** — how many out of 8 agree, weighted by their confidence

**Two modes:**

⚡ **Fast Council** — deterministic checklist-based verdicts, instant. Free.
🤖 **Full Council** — AI writes each persona's thesis in their voice. Slower (~8 LLM calls), counts against your AI quota.

🏆 **Consensus Screener** — finds stocks where almost all 8 personas agree it's a BUY. Across Nifty 100, Midcap 150, and Smallcap 250. Click "Consensus Screener" in the Council nav.

**How to use it:**
1. Go to /agents/RELIANCE (or whatever ticker)
2. See the 8 verdicts at a glance
3. Click any persona to read their full reasoning
4. Use Consensus Screener to find stocks the whole panel likes

**Tip:** If 7+ out of 8 personas say BUY, that's a very strong signal. If they're split 4-4, it usually means the stock is "fair value" — neither cheap nor expensive.`,
    related: ["ai-stock-analyst", "stock-lookup", "tri-factor-scoring"],
  },

  // ── Portfolio & Tracking ──────────────────────────────────────────────────
  {
    id: "portfolio",
    title: "What does the Portfolio page do?",
    keywords: ["portfolio", "holdings", "tradebook", "import", "tax report", "capital gains", "risk", "performance", "valuation", "optimiser", "optimizer"],
    answer: `The **Portfolio** page is where you track your actual holdings — what you own, what it's worth, how it's performing, and what tax you owe.

**Getting your trades in (4 ways):**

📋 **Manual entry** — type each trade one by one
📁 **CSV upload** — drag in a tradebook CSV from any broker
📊 **Excel upload (XLSX)** — same as CSV but works with .xlsx files
🪄 **Screenshot OCR** — take a screenshot of your broker's holdings page, drop it in, AI extracts the rows for you to confirm
🗺️ **Smart mapping wizard** — for unusual broker formats, a 2-step popup lets you map their columns to ours

**What you see once trades are in:**

💰 **Valuation** — current value, total invested, unrealised P&L, % returns
📊 **Performance** — daily / weekly / monthly returns vs NIFTY 50
🎯 **Risk metrics** — portfolio beta, Sharpe ratio, max drawdown, concentration
🧪 **Risk score** — VaR (Value at Risk) at 95% and 99% confidence
⚖️ **Optimiser** — suggests rebalancing to reduce risk or improve returns
🥧 **Sector allocation** — pie chart of where your money is
📈 **Top contributors** — which stocks made you the most / cost you the most

**Tax reports (Indian financial year):**

🧾 **FIFO capital gains** — automatically matches buys and sells using FIFO (First In First Out) — the method the Income Tax Department expects
📅 **Per-FY breakdown** — short-term (< 1 year) vs long-term (≥ 1 year) gains separated
💾 **Download as CSV** — drop straight into your ITR filing
🔁 **Switch FYs** — view any past financial year that has transactions

**Bulk operations:**

🗑️ **Bulk delete** — remove multiple transactions in one click (and the cash balance automatically rolls back)

**How to use it:**
1. Go to /portfolio
2. Click "Import" and pick your method
3. Confirm the parsed transactions
4. Switch to Valuation / Risk / Performance / Tax Report tabs

**Tip:** After importing, run the Optimiser — it often spots concentration risk (too much in one sector or stock) that's easy to fix.`,
    related: ["dcf-valuation", "tri-factor-scoring", "email-digest", "connect-broker"],
  },
  {
    id: "connect-broker",
    title: "Can I connect my brokerage account?",
    keywords: ["broker", "zerodha", "angel one", "dhan", "groww", "upstox", "connect broker", "brokerage", "live positions", "api key"],
    answer: `Yes — the **Settings → Broker Keys** page lets you plug in your brokerage account so the app can read your live holdings, positions, and orders.

**Supported brokers:**

🟢 **Zerodha** (Kite Connect)
🟠 **Angel One** (SmartAPI)
🔵 **Dhan**
🟢 **Groww**
🟡 **Upstox**

**What unlocks once connected:**

💼 **Live portfolio** — your real holdings appear in /portfolio automatically (no manual import needed)
📊 **Positions sync** — open F&O positions show up in the Options Tester
📋 **Order history** — transactions auto-populate for tax reports
🔔 **Smarter alerts** — alerts can reference your actual positions

**Setup:**
1. Go to /settings → Broker Keys
2. Pick your broker
3. Paste in your API key and secret (generate them in your broker's developer portal)
4. Click "Test" — confirms the credentials work
5. Save

**Privacy:**
Keys are encrypted at rest in the database and never exposed in API responses or logs. Each user's keys are tied to their account — admins can't see them.

**No order placement (yet):**
The integrations are read-only. The app does NOT place orders on your behalf. That's intentional — execution is your call, every time.

**How to use it:**
Once connected, just go to Portfolio. Your real holdings appear automatically. No CSV import needed.

**Tip:** Generate a read-only API key in your broker's dev portal if they offer one — there's no need for trade permissions.`,
    related: ["portfolio", "email-digest"],
  },
  {
    id: "dcf-valuation",
    title: "What is DCF Valuation?",
    keywords: ["dcf", "discounted cash flow", "fair value", "valuation", "intrinsic value", "dcf model"],
    answer: `**DCF (Discounted Cash Flow)** is the most respected way to estimate what a stock is "really" worth — independent of what the market is paying for it today.

**The big idea — in plain English:**
A company's value = all the cash it'll make over its lifetime, brought back to today's money. Cash 10 years from now is worth less than cash today (because inflation + you could've invested it elsewhere). DCF does that math for you.

**What the DCF page shows:**

💵 **Estimated fair value per share** — what the stock is theoretically worth
📊 **Current price vs fair value** — is it cheap, expensive, or fair?
📉 **Margin of safety** — how much room you have if your assumptions are wrong
🔧 **Tweak the assumptions** — change growth rate, discount rate, terminal multiple and watch the fair value update live

**The three numbers that matter most:**

1. **Growth rate** — how fast will the company's cash flow grow? (Higher → higher fair value)
2. **Discount rate** — how risky is this company? (Higher → lower fair value)
3. **Terminal value** — what's it worth after the explicit forecast period?

**How to use it:**
1. Go to /dcf (or click the DCF tab inside Stock Lookup)
2. Pick a stock
3. Look at the default fair-value estimate
4. Tweak the growth and discount rate sliders to see how sensitive the answer is
5. Compare fair value to current price — big gap = potential opportunity

**The honest disclaimer:**
DCF is only as good as your assumptions. Two analysts using DCF on the same stock can get wildly different answers. Use it as one input, not the only one.

**Tip:** A DCF that says fair value is 20%+ above current price is a "wide moat" candidate. But always cross-check with the Investor Council's value persona.`,
    related: ["stock-lookup", "tri-factor-scoring", "investor-council"],
  },
  {
    id: "tri-factor-scoring",
    title: "What is Tri-Factor Scoring?",
    keywords: ["tri factor", "tri-factor", "score", "momentum quality value", "stock score", "factor scoring"],
    answer: `**Tri-Factor Scoring** boils a stock down to one 0-100 number — combining the three factors that academic research has consistently shown predict returns.

**The three factors:**

🚀 **Momentum (1/3 weight)**
Is the stock trending up? Looks at recent returns (3-month / 6-month / 12-month), distance from highs, RSI strength.
*Higher = stock has positive momentum.*

💎 **Quality (1/3 weight)**
Is this a well-run business? Looks at ROE (return on equity), debt/equity, earnings consistency, profit margins.
*Higher = better fundamentals.*

💰 **Valuation (1/3 weight)**
Is it cheap relative to peers? Looks at P/E, P/B, EV/EBITDA, dividend yield.
*Higher = cheaper / better value.*

**How to read the score:**

🟢 **80-100** — All-rounder. Cheap + good business + going up. Rare and powerful.
🟢 **60-79** — Solid all-round. Good buy candidate.
🟡 **40-59** — Mixed. Strong on some factors, weak on others — read the breakdown.
🔴 **20-39** — Caution. Multiple red flags.
🔴 **0-19** — Avoid.

**Why three factors and not just one?**
Each factor works in different markets:
  • Momentum dominates in trending markets
  • Quality dominates in bear markets
  • Valuation dominates in recoveries
Combining all three smooths out the bumps.

**In this app:** Tri-Factor Score appears on every Stock Lookup page. Click the score to see the breakdown — which factor is strong, which is weak.

**Tip:** A stock scoring 70+ on quality but only 30 on valuation = "great business but expensive". A stock scoring 80 on momentum but 30 on quality = "running hot, but the business may not justify it". The total score is just the starting point — read the breakdown.`,
    related: ["stock-lookup", "dcf-valuation", "investor-council"],
  },
  {
    id: "email-digest",
    title: "What is the Daily Email Digest?",
    keywords: ["email digest", "daily email", "morning email", "portfolio email", "smtp", "subscribe email"],
    answer: `The **Daily Email Digest** sends a summary of your portfolio and the market straight to your inbox every morning — at the IST time you pick.

**What's in the email:**

💼 **Your portfolio snapshot** — total value, day's P&L, top movers in your holdings
🚀 **Today's market mood** — Macro Pulse highlights, sector rotation phase
🕯️ **Patterns alert** — bullish/bearish signals in stocks you own or watch
📰 **Personalised news** — headlines about your holdings
🎯 **Where to act** — sectors with strong momentum, watchlist stocks near key levels

**Setup:**
1. Go to /email-digest
2. Click "+ New Subscription"
3. Pick your delivery time (e.g. 8:00 AM IST)
4. Choose what to include (portfolio, market, watchlist, news)
5. Save

**Send-now:**
Don't want to wait until tomorrow? Click "Send Now" on any subscription to get the digest immediately.

**Behind the scenes:**
The backend enqueues digests when their send time arrives, then a rate-limited worker dispatches them via SMTP. Every weekday morning, like clockwork.

**How to use it:** Set one up Monday morning. It'll arrive every weekday before market open. If you stop reading it after a week, you don't need it — turn it off.

**Tip:** Set the delivery for 8:45 AM IST. That gives you time to read it before the 9:15 AM market open.`,
    related: ["portfolio", "dashboard", "telegram-bot"],
  },

  // ── Macro, News & Insights ────────────────────────────────────────────────
  {
    id: "insights-page",
    title: "What is the Insights page?",
    keywords: ["insights", "ipo", "ipos", "fii", "dii", "bulk deals", "block deals", "fo ban", "mtf", "slbm", "mutual fund", "mf scheme"],
    answer: `The **Insights** page is the institutional-data hub — the stuff most retail apps don't show but pros watch closely.

**What's on it (tabs):**

🌡️ **Macro tab** — full macro dashboard:
  • RBI Repo Rate history
  • India CPI inflation trend
  • IIP (industrial output)
  • India 10Y G-Sec yield
  • Global indices grid

💸 **FII/DII Flows tab** — what foreign and domestic institutions did today and over time:
  • Cash market (provisional + confirmed)
  • F&O Index (buys/sells in NIFTY/BANKNIFTY futures + options)
  • F&O Stock (single-stock futures + options)

🎯 **IPO Calendar** — every mainboard and SME IPO currently open or upcoming:
  • Issue dates, price band, lot size
  • Subscription numbers in real-time
  • GMP (Grey Market Premium) where available

📋 **F&O Ban List** — stocks currently in F&O ban (no new positions allowed). Updates daily after market close.

🤝 **Bulk & Block Deals** — large trades reported to NSE/BSE. Often signals institutional moves.

💼 **SLBM** — Stock Lending & Borrowing data. High SLBM borrow demand often precedes short-selling pressure.

📊 **MTF (Margin Trading Facility)** — outstanding MTF positions in each stock. Spikes can mean retail leverage building up.

📈 **Mutual Fund schemes** — search any MF scheme code, get NAV history, returns ladder (1Y / 3Y / 5Y / 10Y / since launch), portfolio composition.

**How to use it:**
1. Go to /insights
2. Switch between tabs at the top
3. Click into any item for detail

**Tip:** Watch FII selling + DII buying — that's typically a market that's about to bottom. The reverse (FII buy + DII sell) often happens near tops.`,
    related: ["macro-pulse", "fii-dii", "dashboard"],
  },
  {
    id: "macro-pulse",
    title: "What is the Macro Pulse?",
    keywords: ["macro pulse", "macro", "rbi repo rate", "cpi", "iip", "10y yield", "g-sec", "inflation", "interest rates", "fred"],
    answer: `**Macro Pulse** is the strip at the top of the Dashboard — and a full page under Insights → Macro — showing the state of the Indian economy in one glance.

**The six tiles:**

🏛️ **RBI Repo Rate** — the rate at which RBI lends to banks. Higher → loans get expensive, stocks usually fall.

📈 **India CPI** — Consumer Price Inflation. Rising CPI → RBI may hike rates → stocks under pressure.

🏭 **IIP** — Index of Industrial Production. Higher → economy growing → bullish for stocks.

📜 **India 10Y G-Sec Yield** — the government's 10-year bond yield. Rising yields → "stocks need higher returns to compete" → pressure on stock valuations.

💵 **USD/INR** — exchange rate. Weaker rupee → IT/pharma (exporters) benefit, FMCG/auto (importers) hurt.

🛢️ **Brent Crude** — oil price. Higher oil → inflation worry → bearish for India broadly.

**Why this matters for a stock investor:**
Even the best company gets hammered in a bad macro environment. The Macro Pulse is your "is the wind at my back or in my face" check.

**Data sources:**
RBI rates and 10Y yield come from FRED (the US Federal Reserve's free data API). CPI/IIP from World Bank + official India sources. Updated hourly.

**The "What changed this week" commentary** — under Insights → Macro — uses AI to explain in plain English what moved and what it means.

**How to use it:** Glance at it once in the morning. If all six are red or trending bad, scale back risk. If they're green, lean in.`,
    related: ["dashboard", "fii-dii", "insights-page"],
  },
  {
    id: "fii-dii",
    title: "What are FII / DII flows?",
    keywords: ["fii", "dii", "foreign investors", "domestic investors", "institutional flows", "fpi", "smart money"],
    answer: `**FII / DII flows** show whether the big money is buying or selling Indian stocks.

**FII = Foreign Institutional Investor**
Includes US/UK/Japan pension funds, hedge funds, sovereign wealth funds (Norway, GIC, ADIA, etc.). They control trillions of dollars and move markets when they act in unison.

**DII = Domestic Institutional Investor**
Indian mutual funds, insurance companies (LIC, HDFC Life), and pension funds. Their inflows usually come from SIPs (your monthly mutual fund auto-debit) — which is why DII flows are often steady while FII flows are volatile.

**What you see in the app:**

📊 **Daily net buy/sell** in:
  • Cash market — actual stock buying/selling
  • F&O Index — futures & options on NIFTY / BANKNIFTY
  • F&O Stock — futures & options on individual stocks

📈 **30-day rolling chart** — see the trend, not just today's number

📋 **Segment breakdown** — provisional (end-of-day estimate) and confirmed (next-day final)

**The classic "smart money" pattern:**

🟢 **FII selling + DII buying** = market often near a bottom (foreigners panicking, locals buying the dip — locals usually right)

🔴 **FII buying + DII selling** = market often near a top (foreigners chasing, locals taking profits — locals usually right)

**In this app:** Find FII/DII flows on the Insights page → FII/DII tab. The data refreshes every 4 hours.

**Tip:** Don't trade on a single day's FII number — they're noisy. Look at 5-day or 10-day rolling sums for trends.`,
    related: ["insights-page", "macro-pulse", "dashboard"],
  },
  {
    id: "news-feed",
    title: "What is the News Feed?",
    keywords: ["news", "news feed", "headlines", "market news", "company news", "earnings news"],
    answer: `The **News Feed** is your live financial news ticker — pulling from RSS feeds across major Indian financial publications and tagging each article with sentiment + companies mentioned.

**What you get:**

📰 **Latest headlines** — markets, companies, economy, regulation
🏷️ **Entity tags** — every article auto-tagged with the stocks it mentions (using spaCy NER)
😀 **Sentiment score** — positive / neutral / negative (using VADER + LLM scoring)
🔍 **Filter by stock** — click a ticker to see only news about that company
🗂️ **Filter by category** — markets / economy / IPO / earnings / regulation / global
🌐 **Source link** — every story links back to the original publisher

**Bonus on the Stock Lookup page:**
Open any stock and you'll see the latest ticker-specific news in a side panel — same data, just pre-filtered.

**For deeper analysis:**
The AI Stock Analyst pulls from this same news feed plus Tavily web search (for mid/small caps where RSS coverage is thin) to write the "News" section of its reports.

**How to use it:** Check it in the morning. If a stock you own is in the headlines, drill in. If sentiment turned sharply negative on a sector overnight, expect volatility on open.`,
    related: ["sentiment-dashboard", "stock-lookup", "ai-stock-analyst"],
  },
  {
    id: "sentiment-dashboard",
    title: "What is the Sentiment Dashboard?",
    keywords: ["sentiment", "market sentiment", "sector sentiment", "mood", "fear greed", "vader"],
    answer: `The **Sentiment Dashboard** measures the market's mood — how bullish or bearish people are feeling, right now, based on news, social signals, and price action.

**What it shows:**

🌡️ **Overall market sentiment** — a single score (very bearish → bearish → neutral → bullish → very bullish) refreshed every 15 minutes

🏭 **Per-sector sentiment heatmap** — green for bullish sectors, red for bearish. Lets you see WHERE the optimism (or fear) is.

📰 **What's driving it** — the top headlines pushing sentiment up or down today

📈 **Sentiment trend** — how the score has moved over the past week

**How sentiment is calculated:**
A mix of:
  • News headlines (VADER + LLM scoring)
  • Price action vs moving averages
  • Advance/decline ratio
  • Volume patterns
  • Pattern detections (lots of bullish patterns = bullish sentiment)

**The contrarian playbook:**
Extreme sentiment usually reverses.
  • "Very bullish" + everyone talking about how easy it is = often a top
  • "Very bearish" + everyone panicking = often a bottom

**In this app:** Open /sentiment for the full view. The Dashboard shows a condensed version.

**Tip:** Sentiment in any single sector that diverges from the market is interesting — if the market is neutral but Pharma sentiment is "very bullish", that's worth a look.`,
    related: ["news-feed", "dashboard", "macro-pulse"],
  },

  // ── Bots & Alerts ─────────────────────────────────────────────────────────
  {
    id: "telegram-bot",
    title: "How does the Telegram Bot work?",
    keywords: ["telegram", "telegram bot", "telegram alerts", "chatbot", "mobile alerts"],
    answer: `The **Telegram Bot** lets you ask the market anything from your phone — without opening the app.

**What you can do:**

💬 **Quotes** — type "TCS" or "Reliance" → instant price + technical summary
🕯️ **Patterns** — "show bullish patterns" → today's signals
📊 **Sector rotation** — "where to invest" → current rotation analysis
🔍 **Scanners** — "run golden cross" → executes scanner
🤖 **AI questions** — "is HDFC Bank a buy?" → routes to AI Analyst
🔔 **Alerts** — set up price/pattern alerts (see Bot Alerts)
📰 **Sector rotation push** — get the daily rotation analysis sent to you automatically

**Setup:**
1. On Telegram, search **@NiftyNodeBot** (or whatever bot your admin configured)
2. Hit **/start**
3. Link your account (the bot will ask for your verification code from /settings)
4. Done — chat away

**Commands you'll use most:**
  • Just type a stock ticker
  • "/help" → list everything
  • "/alerts" → manage your alerts
  • "/portfolio" → snapshot of your holdings

**How it works:**
The bot long-polls Telegram for new messages, routes each to the same NLP engine that powers Hydra Alpha, and sends the response back. Same intelligence as the web app — just delivered through Telegram.

**Tip:** Add the bot to a group with friends if you want a shared market chat that can actually answer questions.`,
    related: ["whatsapp-bot", "bot-alerts", "ai-analyzer"],
  },
  {
    id: "whatsapp-bot",
    title: "How does the WhatsApp Bot work?",
    keywords: ["whatsapp", "whatsapp bot", "whatsapp alerts", "twilio", "qr code"],
    answer: `The **WhatsApp Bot** is the same intelligence as the Telegram bot — delivered through WhatsApp.

**What you can do:**
Everything the Telegram bot does — quotes, patterns, scanners, alerts, sector rotation pushes — but in WhatsApp.

**Setup (because WhatsApp is stricter than Telegram):**
1. Go to /settings → WhatsApp Bot section
2. Click "Generate QR Code"
3. Scan the QR with WhatsApp on your phone
4. The bot replies with a verification — confirm to link your account
5. Done — send messages directly

**Or with Twilio's WhatsApp sandbox:**
1. Send "join <sandbox-code>" to Twilio's WhatsApp number (your admin will share this)
2. The bot replies, link your account
3. Chat away

**Why two bots?**
  • **Telegram** — easier setup, more features, free
  • **WhatsApp** — what most people in India already use, but Twilio billing applies

**Limitations:**
WhatsApp has stricter media + interactive message rules than Telegram, so some richer features (inline buttons, in-message charts) work better on Telegram.

**How to use it:** Pick one bot, stick with it. Most users prefer Telegram for power use and WhatsApp for casual quotes.`,
    related: ["telegram-bot", "bot-alerts"],
  },
  {
    id: "bot-alerts",
    title: "How do I set up price alerts?",
    keywords: ["alerts", "price alert", "bot alert", "notification", "watchlist alert", "telegram alert"],
    answer: `**Bot Alerts** let you get notified — via Telegram or WhatsApp — when a stock hits a price, a pattern fires, or a scanner finds a new match.

**Types of alerts:**

🎯 **Price alert** — "ping me when RELIANCE crosses ₹3000"
🕯️ **Pattern alert** — "tell me if any Nifty 100 stock prints a bullish engulfing"
🔍 **Scanner alert** — "run my Golden Cross scanner every morning and notify if there are matches"
📊 **Sector alert** — "tell me when IT sector goes red 3+ days in a row"

**Setup (from Telegram or WhatsApp):**
1. Send "/alerts" or "set alert" to the bot
2. The bot walks you through picking the alert type
3. Confirm — you'll get a confirmation reply

**Or from the web:**
Open any stock in Stock Lookup → click the 🔔 bell icon → set the threshold.

**How alerts fire:**
Every alert subscription is evaluated every 5 minutes during market hours. When a condition is met, the alert is dispatched via your chosen channel (Telegram or WhatsApp), then auto-disabled (so you don't get spammed every 5 minutes).

**Managing alerts:**
Send "/alerts list" to the bot, or visit /settings → Alerts in the web app.

**Tip:** Don't over-alert. Setting 20 alerts means you'll ignore the one that actually matters. Pick 3-5 high-value conditions.`,
    related: ["telegram-bot", "whatsapp-bot", "patterns-page"],
  },

  // ── Market Concepts ───────────────────────────────────────────────────────
  {
    id: "stock-market",
    title: "What is the stock market?",
    keywords: ["stock market", "share market", "what is stock", "what is share", "how does market work", "nse", "bse", "sensex"],
    answer: `The **stock market** is a place where companies sell small pieces of ownership — called **shares** or **stocks** — and anyone can buy or sell them.

**In simple terms:**
  • A company needs money to grow → it lists on the stock exchange
  • You buy a share → you own a tiny piece of that company
  • If the company does well → share price goes up → you make profit
  • If it does poorly → share price falls → you lose money

**India has two main exchanges:**

🔵 **NSE (National Stock Exchange)** — largest by volume. Index = **NIFTY 50** (top 50 companies)
🔴 **BSE (Bombay Stock Exchange)** — oldest in Asia. Index = **SENSEX** (top 30 companies)

**Market timing:** 9:15 AM – 3:30 PM, Monday to Friday (IST)

**Who participates?** Retail investors (like you), large funds (mutual funds, FIIs), and traders (who buy/sell frequently).

**The key rule:** Prices go UP when more people want to BUY than sell. Prices go DOWN when more people want to SELL than buy.`,
    related: ["nifty", "market-cap", "how-to-invest"],
  },
  {
    id: "nifty",
    title: "What is NIFTY 50?",
    keywords: ["nifty", "nifty 50", "sensex", "index", "benchmark", "nse index"],
    answer: `**NIFTY 50** is an index — a basket of the 50 largest companies listed on NSE.

**Think of it like a report card for the Indian economy.**
When NIFTY goes up, it means those 50 big companies are collectively doing well.
When NIFTY falls, those companies are losing value.

**How it's calculated:**
NIFTY is weighted by market capitalisation — bigger companies (like Reliance, TCS, HDFC Bank) have more influence on the index value.

**Other important NIFTY indices:**
  • **NIFTY BANK** — top banking stocks
  • **NIFTY IT** — IT companies (TCS, Infosys, Wipro)
  • **NIFTY PHARMA** — pharmaceutical companies
  • **NIFTY MIDCAP** — mid-sized companies

**SENSEX** is BSE's version — it tracks the top 30 companies instead of 50. Both move in a similar direction most of the time.

**In this app:** The sectors page tracks NIFTY sector indices in real time.`,
    related: ["stock-market", "sector-rotation", "what-sector"],
  },
  {
    id: "rsi",
    title: "What is RSI?",
    keywords: ["rsi", "relative strength index", "overbought", "oversold", "rsi indicator", "rsi 14", "momentum indicator"],
    answer: `**RSI (Relative Strength Index)** is a number between 0 and 100 that tells you how fast a stock has been moving.

**Easy way to remember it:**

📈 **RSI above 70 = Overbought**
The stock has moved up very fast. It might be due for a rest or a pullback. Be cautious buying here.

📉 **RSI below 30 = Oversold**
The stock has fallen a lot, very fast. It might be due for a bounce. Potential buying opportunity.

⚖️ **RSI between 40 and 60 = Neutral / Healthy**
The stock is moving normally. No extreme in either direction.

**Example:**
If RELIANCE has RSI = 72, it means buyers have been very aggressive recently. The stock may be getting "too hot" and could pull back slightly before the next leg up.

**Important:** RSI above 70 doesn't mean sell immediately. In a strong uptrend, RSI can stay above 70 for weeks. Use it alongside price action and other indicators.

**In this app:** Stock Lookup shows RSI for every stock. Chart Studio shows RSI as a graph below the main chart.`,
    related: ["macd", "moving-averages", "stock-lookup"],
  },
  {
    id: "macd",
    title: "What is MACD?",
    keywords: ["macd", "macd indicator", "moving average convergence", "macd signal", "macd histogram", "crossover"],
    answer: `**MACD (Moving Average Convergence Divergence)** is a trend indicator that shows the relationship between two moving averages.

**Three components:**

1. **MACD Line** — difference between the 12-day and 26-day averages
2. **Signal Line** — 9-day average of the MACD line
3. **Histogram** — the gap between the MACD line and Signal line

**How to read it:**

✅ **MACD crosses ABOVE the Signal line** → Bullish signal. The short-term trend is picking up strength. Consider buying.

❌ **MACD crosses BELOW the Signal line** → Bearish signal. Momentum is slowing. Consider reducing position.

📊 **Histogram growing taller** → Trend is strengthening
📉 **Histogram shrinking** → Trend is weakening

**Why traders love it:** MACD catches trend changes early — before price makes a big visible move.

**Limitation:** MACD can give false signals in sideways markets. It works best when a stock is clearly trending.

**In this app:** Stock Lookup shows the MACD crossover signal for each stock.`,
    related: ["rsi", "moving-averages", "chart-studio"],
  },
  {
    id: "moving-averages",
    title: "What are moving averages?",
    keywords: ["moving average", "ema", "sma", "ma", "200 ema", "50 ema", "20 ema", "golden cross", "death cross", "exponential moving average"],
    answer: `A **moving average (MA)** smooths out a stock's price history so you can see the actual trend — without the day-to-day noise.

**Two types:**

📌 **SMA (Simple Moving Average)** — plain average of the last N closing prices. All days get equal weight.

📌 **EMA (Exponential Moving Average)** — more weight given to recent prices. Reacts faster to new data.

**Common moving averages:**
  • **20-day EMA** — short-term trend (used by traders)
  • **50-day EMA** — medium-term trend (most popular)
  • **200-day EMA** — long-term trend (used by investors)

**Key rules:**

✅ **Price above 50 EMA** → medium-term trend is UP
❌ **Price below 50 EMA** → medium-term trend is DOWN

**Golden Cross** — when the 50-day EMA crosses ABOVE the 200-day EMA → very strong long-term bullish signal. Markets often rally for months after.

**Death Cross** — when the 50-day EMA crosses BELOW the 200-day EMA → long-term bearish signal.

**In this app:** Stock Lookup shows whether price is above/below key EMAs. The Scanners page has a Golden Cross scanner.`,
    related: ["rsi", "macd", "scanners-page"],
  },
  {
    id: "candlestick",
    title: "What are candlestick patterns?",
    keywords: ["candlestick", "candle", "candlestick pattern", "bullish candle", "bearish candle", "hammer", "doji", "engulfing", "morning star", "evening star", "shooting star"],
    answer: `**Candlestick charts** show price movement in a visual way. Each "candle" represents one time period (1 day, 1 hour, etc.).

**Reading a single candle:**

🟢 **Green candle** (or white) → price closed HIGHER than it opened. Bulls won.
🔴 **Red candle** (or black) → price closed LOWER than it opened. Bears won.

Each candle has:
  • **Body** — the thick part (open to close)
  • **Upper shadow (wick)** — how high price went during the period
  • **Lower shadow (wick)** — how low price went during the period

**Common patterns and what they mean:**

🟢 **Bullish patterns (possible UP move):**
  • **Hammer** — long lower wick, small body at the top. Buyers rejected the low prices.
  • **Morning Star** — 3-candle reversal: red → small → green. Downtrend ending.
  • **Bullish Engulfing** — big green candle covers the previous red candle entirely.

🔴 **Bearish patterns (possible DOWN move):**
  • **Shooting Star** — long upper wick, small body at the bottom. Buyers failed to hold highs.
  • **Evening Star** — 3-candle reversal: green → small → red. Uptrend ending.
  • **Bearish Engulfing** — big red candle covers the previous green candle entirely.

**In this app:** The Patterns page scans 500+ stocks daily and lists all detected patterns automatically.`,
    related: ["patterns-page", "chart-studio"],
  },
  {
    id: "what-sector",
    title: "What is a sector?",
    keywords: ["sector", "what is sector", "industry", "sector investing", "which sector", "nifty sector"],
    answer: `The stock market is grouped into **sectors** — collections of companies in the same industry.

**Main Indian market sectors:**

🖥️ **IT (Information Technology)** — TCS, Infosys, Wipro, HCL Tech
🏦 **Banking** — HDFC Bank, ICICI Bank, SBI, Kotak
💊 **Pharma** — Sun Pharma, Cipla, Dr Reddy's, Lupin
🚗 **Auto** — Maruti, Tata Motors, Hero MotoCorp, Bajaj Auto
🛒 **FMCG** — HUL, ITC, Nestlé, Dabur, Britannia
⚙️ **Metal** — Tata Steel, JSW Steel, Hindalco, SAIL
⚡ **Energy** — ONGC, BPCL, Power Grid, Adani Green
🏠 **Realty** — DLF, Godrej Properties, Prestige
🏥 **Healthcare** — Apollo Hospitals, Fortis, Max Health

**Why sectors matter:**
When a sector is strong, most stocks inside it tend to rise together. If IT sector is up 2%, individual IT stocks are more likely to go up too.

This is why experienced traders always check sector performance FIRST before picking individual stocks.

**In this app:** The Market Sectors page shows all sectors and their performance in real time.`,
    related: ["sectors-page", "sector-rotation", "dashboard"],
  },
  {
    id: "sector-rotation",
    title: "What is sector rotation?",
    keywords: ["sector rotation", "rotation", "where to invest", "money flowing", "market cycle", "hot sector", "outperform", "underperform"],
    answer: `**Sector rotation** is the movement of money from one sector of the market to another, as the economic cycle changes.

**The idea:** Big investors (mutual funds, FIIs) constantly shift money into sectors they expect to do well and out of sectors they expect to do poorly.

**How it works through the economic cycle:**

🌅 **Early recovery** → Banking, Real Estate, and Consumer Discretionary lead
☀️ **Expansion** → IT, Auto, and Industrials do well
🌇 **Late cycle (slowdown)** → FMCG, Pharma, and Healthcare outperform (defensive)
🌑 **Recession** → Only Utilities and Gold hold up

**Simple rule of thumb:**
  • If FII (foreign investors) are buying → market is likely to rise
  • If IT and Banking are both strong → broad bull market
  • If FMCG and Pharma outperform everything → the market is getting cautious

**In this app:**
  • The **Dashboard** shows the current market phase and rotation signal
  • The **AI Analyzer** answers "where should I invest?" by showing rotation data
  • The **Market Sectors** page lets you track which sectors are gaining momentum`,
    related: ["dashboard", "what-sector", "sectors-page", "market-phase"],
  },
  {
    id: "market-phase",
    title: "What are the market phases?",
    keywords: ["market phase", "bull market", "bear market", "market cycle", "early bull", "full bull", "slowdown", "recession"],
    answer: `Markets move through repeating **phases** — understanding where you are in the cycle helps you make better decisions.

**The 4 main phases:**

🌱 **Early Bull Market**
  → Market recovering after a fall. Smart money starts buying.
  → What to do: Start buying quality stocks in strong sectors

🚀 **Full Bull Market**
  → Everything is going up. Good news everywhere. Retail investors pile in.
  → What to do: Ride the trend, but don't get overconfident. Set stop-losses.

🌅 **Late Cycle / Slowdown**
  → Growth slowing. Defensive sectors (FMCG, Pharma) start outperforming.
  → What to do: Reduce risk. Move some money to safer sectors.

🐻 **Bear Market**
  → Broad decline. Most stocks falling. Fear in the market.
  → What to do: Protect capital. Wait for the cycle to bottom out.

**In this app:** The **Dashboard** shows the current market phase at the top (e.g. "Late Cycle / Slowdown"). The sector rotation analysis below it explains what the data is suggesting you do right now.`,
    related: ["dashboard", "sector-rotation", "what-sector"],
  },
  {
    id: "market-cap",
    title: "What is market cap?",
    keywords: ["market cap", "market capitalisation", "market capitalization", "large cap", "mid cap", "small cap", "big company"],
    answer: `**Market Cap (Market Capitalisation)** = Share price × Total number of shares

It tells you the total value the market places on a company.

**The three categories in India:**

🏦 **Large Cap** — Market cap above ₹20,000 crore
  → Examples: Reliance, TCS, HDFC Bank
  → More stable, less risky, lower growth potential
  → Good for long-term investors

📈 **Mid Cap** — Market cap ₹5,000 – ₹20,000 crore
  → Examples: Voltas, Trent, Persistent Systems
  → Higher growth potential, moderate risk
  → Good for medium-term investors

🚀 **Small Cap** — Market cap below ₹5,000 crore
  → High risk, high potential reward
  → Can give multi-bagger returns OR fall 60-70%
  → Only for experienced investors with high risk tolerance

**Simple rule:** Start with large caps (safer). Gradually add mid caps as you learn. Small caps only when you understand the business well.`,
    related: ["stock-market", "stock-lookup"],
  },
  {
    id: "volume",
    title: "What is trading volume?",
    keywords: ["volume", "trading volume", "high volume", "low volume", "volume spike", "daily volume"],
    answer: `**Volume** = the number of shares traded in a given time period (a day, an hour, etc.)

**Why volume matters:**

✅ **High volume + price rising** → Strong move. Buyers are serious. Trend likely to continue.
✅ **High volume + price falling** → Strong selling. Bears are serious. Decline likely to continue.

⚠️ **Low volume + price rising** → Weak rally. Not many people trust the move. Could reverse easily.
⚠️ **Low volume + price falling** → Weak selling. Likely temporary. Could bounce.

**Volume spikes** — when volume is 3-5x higher than usual:
  → Often signals a big announcement, breakout, or institutional buying/selling
  → This is the signal the Scanners page looks for in the "Volume Spike" scanner

**How to use volume:**
Always check volume to confirm a price move. A big green candle on LOW volume is suspicious. A big green candle on HIGH volume is trustworthy.

**In this app:** The Scanners page has a Volume Spike scanner that finds stocks with unusual activity.`,
    related: ["scanners-page", "chart-studio"],
  },
  {
    id: "pe-ratio",
    title: "What is P/E ratio?",
    keywords: ["pe ratio", "p/e ratio", "price to earnings", "pe", "valuation", "overvalued", "undervalued", "earnings"],
    answer: `**P/E Ratio (Price-to-Earnings)** tells you how much you're paying for every ₹1 of a company's annual profit.

**Formula:** Current stock price ÷ Earnings per share (EPS)

**Example:**
  → Stock price: ₹500
  → Annual earnings per share: ₹25
  → P/E ratio = 500 ÷ 25 = **20**
  → You're paying ₹20 for every ₹1 of profit

**How to interpret it:**

📉 **Low P/E** (compared to sector average) → Potentially undervalued. Could be a bargain — OR the company has serious problems.

📈 **High P/E** → Market expects fast future growth. Expensive, but growth stocks often deserve high P/E.

🔍 **Always compare P/E with:**
  1. The stock's own historical P/E (is it cheap or expensive vs its past?)
  2. The sector's average P/E (is IT at 30 P/E expensive? Yes. Is pharma at 30 P/E expensive? Maybe not.)

**Indian context:** NIFTY 50 historically trades at 20-25x P/E. Above 25 = expensive. Below 18 = attractive.`,
    related: ["stock-lookup", "market-cap"],
  },
  {
    id: "call-put",
    title: "What are Call and Put options?",
    keywords: ["call option", "put option", "call", "put", "what is option", "options", "derivative", "f&o", "futures and options"],
    answer: `**Options** are contracts that give you the right (but not the obligation) to buy or sell a stock at a fixed price before a certain date.

**Two types:**

📗 **Call Option** — right to BUY at a fixed price
  → You buy a Call when you think the stock will go UP
  → If the stock rises above your strike price → you profit
  → If it doesn't → you only lose the premium you paid (small amount)

📕 **Put Option** — right to SELL at a fixed price
  → You buy a Put when you think the stock will go DOWN
  → If the stock falls below your strike price → you profit
  → If it doesn't → you only lose the premium

**Key terms:**
  • **Strike price** — the fixed price in the contract
  • **Premium** — the price you pay to buy the option
  • **Expiry** — the date the contract ends (NIFTY expires every Thursday)
  • **In The Money (ITM)** — option has intrinsic value right now
  • **At The Money (ATM)** — strike price = current stock price
  • **Out of The Money (OTM)** — option has no immediate value but could gain

**In this app:** The **Options Tester** lets you build and test any options strategy without real money.`,
    related: ["greeks", "iv", "options-tester", "iron-condor", "straddle"],
  },
  {
    id: "greeks",
    title: "What are the Options Greeks?",
    keywords: ["greeks", "delta", "gamma", "theta", "vega", "rho", "options greeks", "option price"],
    answer: `**The Greeks** are five numbers that tell you exactly how an option's price will behave. Each one measures a different risk.

**Δ Delta — directional risk**
How much the option price changes for a ₹1 move in the stock.
  → Delta of 0.5 = if stock rises ₹10, option gains ₹5
  → Calls have positive delta (gain when stock rises)
  → Puts have negative delta (gain when stock falls)

**Θ Theta — time decay**
How much the option loses value every single day as it gets closer to expiry.
  → Buying options = Theta hurts you (value melts away daily)
  → Selling options = Theta helps you (you collect the daily decay)

**ν Vega — volatility sensitivity**
How much the option price changes for a 1% change in implied volatility.
  → High VIX (fear) = options become expensive = high Vega

**Γ Gamma — how fast delta changes**
  → High near expiry: small price moves cause huge changes in option value

**ρ Rho — interest rate sensitivity**
  → Least important for typical Indian options (monthly/weekly expiry)

**In this app:** The Options Tester shows all 5 Greeks for your strategy after you click "Analyse Strategy".`,
    related: ["call-put", "iv", "options-tester", "theta-decay"],
  },
  {
    id: "iv",
    title: "What is implied volatility?",
    keywords: ["implied volatility", "iv", "volatility", "vix", "india vix", "iv percentile", "options expensive", "options cheap"],
    answer: `**Implied Volatility (IV)** is the market's best guess about how much a stock will move in the future.

**Simple way to think about it:**
IV is the "fear/excitement" level baked into option prices.

📈 **High IV** → Options are expensive. Market expects big moves (could be up OR down).
  → Good time to SELL options (collect the high premium)

📉 **Low IV** → Options are cheap. Market expects calm, small moves.
  → Good time to BUY options (pay less premium)

**India VIX** — NSE's fear index for NIFTY options
  → VIX above 20 = high fear, expensive options
  → VIX below 12 = calm market, cheap options

**IV vs Historical Volatility (HV):**
  • HV = actual past price movement (what DID happen)
  • IV = expected future movement (what MIGHT happen)
  If IV is much higher than HV → options may be overpriced

**Real world example:**
Before Budget day or RBI policy announcement → IV spikes because nobody knows what will happen. After the event → IV collapses (called "IV crush"). Option buyers often lose money even if they were right about the direction.

**In this app:** The Options Tester uses 30-day Historical Volatility (HV30) as the default IV for each stock.`,
    related: ["call-put", "greeks", "options-tester"],
  },
  {
    id: "iron-condor",
    title: "What is an Iron Condor?",
    keywords: ["iron condor", "condor", "neutral strategy", "credit spread", "range bound"],
    answer: `The **Iron Condor** is a neutral options strategy — you profit when the stock STAYS in a price range.

**Structure — 4 legs:**
1. SELL an OTM Call (e.g. at 1% above current price)
2. BUY a further OTM Call (e.g. at 2% above) — caps your loss
3. SELL an OTM Put (e.g. at 1% below)
4. BUY a further OTM Put (e.g. at 2% below) — caps your loss

**P&L:**
  ✅ **Max Profit** = the total credit received (if stock stays between your short strikes at expiry)
  ❌ **Max Loss** = wing width minus the credit (if stock breaks far above or below)
  📍 **Two breakeven points** — one above, one below the current price

**Best market conditions:**
  → Low volatility, range-bound market
  → VIX below 15
  → No major events expected before expiry

**Risk:** A sudden large move (election result, RBI surprise) can blow out the position quickly.

**In this app:** Load the Iron Condor preset in the Options Tester with one click, then click "Analyse Strategy" to see the payoff chart and your exact breakeven prices.`,
    related: ["options-tester", "call-put", "greeks", "iv", "straddle"],
  },
  {
    id: "straddle",
    title: "What is a Straddle?",
    keywords: ["straddle", "long straddle", "short straddle", "atm straddle"],
    answer: `A **Straddle** is an options strategy where you trade BOTH a call and a put at the same strike price (usually ATM — at the current price).

**Long Straddle** (buy both call and put):
  → Use when you expect a BIG move but don't know which direction
  → Perfect for: Budget day, RBI policy, election results, earnings
  → Max profit: Unlimited (if the move is big enough)
  → Max loss: The total premium paid (if stock doesn't move at all)
  → Theta hurts you — every day without a move costs money

**Short Straddle** (sell both call and put):
  → Use when you expect NO big move — a calm, range-bound market
  → Max profit: The total premium collected
  → Max loss: Unlimited (if stock makes a huge move either way)
  → Theta works FOR you — every quiet day = profit

**Which to use?**
  → Event coming up + uncertainty → Long Straddle
  → Calm week, nothing expected → Short Straddle (with caution)

**In this app:** Both Long and Short Straddle are available as presets in the Options Tester.`,
    related: ["options-tester", "iron-condor", "call-put", "iv"],
  },
  {
    id: "entry-signal",
    title: "What is an entry/exit signal?",
    keywords: ["entry", "exit", "signal", "buy signal", "sell signal", "entry signal", "entry point", "when to buy", "when to sell", "stop loss", "target"],
    answer: `An **entry signal** is a combination of technical indicators that suggests it might be a good time to buy a stock. An **exit signal** tells you when to sell.

**Common entry signals (buy):**
  ✅ Price crosses above the 50-day EMA
  ✅ MACD crosses above the signal line
  ✅ RSI bounces from below 30 (oversold → recovery)
  ✅ A bullish candlestick pattern appears (hammer, morning star)
  ✅ Stock breaks above a key resistance level with high volume

**Common exit signals (sell):**
  ❌ RSI goes above 70 and starts falling
  ❌ Price falls below the 50-day EMA
  ❌ MACD crosses below the signal line
  ❌ A bearish candlestick pattern appears (shooting star, evening star)

**Stop Loss** — a price level where you exit the trade if it goes wrong, to limit your loss. Always set a stop loss before entering.

**Target** — the price where you plan to take profit.

**Risk:Reward ratio** — aim for at least 1:2 (risk ₹100 to make ₹200).

**In this app:** Stock Lookup shows an Entry Signal for every stock — BUY, SELL, or HOLD — based on a combination of RSI, MACD, and EMAs.`,
    related: ["rsi", "macd", "moving-averages", "stock-lookup"],
  },
  {
    id: "support-resistance",
    title: "What are support and resistance?",
    keywords: ["support", "resistance", "support level", "resistance level", "price level", "breakout", "breakdown"],
    answer: `**Support** and **Resistance** are price levels where a stock tends to stop and reverse.

**Support** — a price floor where buying demand appears
  → The stock has bounced from this level multiple times before
  → Buyers step in here, preventing further falls
  → If broken, support becomes resistance

**Resistance** — a price ceiling where selling pressure appears
  → The stock has struggled to go above this level before
  → Sellers appear here, capping the upside
  → If broken, resistance becomes support

**Why they exist:** Many traders remember past price levels. When the stock returns to a previous low, many think "it bounced from here before" → they buy. This self-fulfilling behaviour creates support.

**Breakout** — when price breaks ABOVE resistance with high volume → very bullish signal. The next resistance level becomes the new target.

**Breakdown** — when price breaks BELOW support → bearish signal. The next support level becomes the new target.

**How to find them:**
  → Look at past price charts for areas where price bounced multiple times
  → The more times a level was tested, the stronger it is

**In this app:** Stock Lookup shows nearest support and resistance levels for each stock automatically.`,
    related: ["chart-studio", "candlestick", "volume"],
  },
  {
    id: "how-to-invest",
    title: "How do I start investing in stocks?",
    keywords: ["how to invest", "start investing", "beginner", "first time", "how to buy shares", "demat", "broker", "open account"],
    answer: `Here's a simple step-by-step guide to start investing in Indian stocks:

**Step 1: Open a Demat + Trading account**
  → Use a broker like Zerodha, Upstox, Groww, or Angel One
  → You need: PAN card, Aadhaar, bank account
  → Takes 1-2 days to activate

**Step 2: Add funds to your account**
  → Transfer money from your bank to your trading account via UPI or NEFT

**Step 3: Pick your first stocks**
  → Start with LARGE CAP stocks only (Reliance, TCS, HDFC Bank, Infosys)
  → These are well-known companies with lower risk
  → Avoid penny stocks and unknown small caps initially

**Step 4: Start small**
  → Invest only money you won't need for 3-5 years
  → Don't invest your emergency fund
  → Start with ₹5,000 – ₹10,000 to learn without too much stress

**Step 5: Learn as you go**
  → Use this app to understand sectors, patterns, and technical signals
  → Read one stock-related article per day
  → Never invest based on tips from social media

**Golden rules:**
  🎯 Diversify — don't put all money in one stock
  🛑 Always set a stop loss
  📅 Think long-term — the best returns come from holding quality stocks for years`,
    related: ["stock-market", "market-cap", "rsi", "what-sector"],
  },

  // ── Market Breadth ───────────────────────────────────────────────────────
  {
    id: "ad-ratio",
    title: "What is the Advance/Decline (AD) ratio?",
    keywords: [
      "ad ratio", "a/d ratio", "ad line", "advance decline", "advance/decline",
      "advances", "declines", "advancing", "declining", "market breadth", "breadth",
      "adv dec", "adv/dec", "ad", "a d ratio",
    ],
    answer: `The **Advance/Decline (AD) Ratio** — sometimes called *market breadth* — tells you how many stocks went UP today versus how many went DOWN.

**Formula:**
\`AD Ratio = Number of advancing stocks ÷ Number of declining stocks\`

**How to read it:**

📗 **AD Ratio > 1** → More stocks are rising than falling. The rally is broad and healthy.
  • > 2 = very strong, broad-based buying
  • 1 – 2 = mildly positive

⚖️ **AD Ratio ≈ 1** → Mixed market. Roughly equal winners and losers — no clear direction.

📕 **AD Ratio < 1** → More stocks are falling than rising. Selling pressure is widespread.
  • < 0.5 = broad-based fear

**Why it matters:**
The Nifty 50 can go up because just 5 big stocks rallied — that looks bullish on the surface but is actually weak. The AD Ratio cuts through the noise: if the index is up 1% but only 30% of stocks advanced, the rally is **narrow and fragile**.

**In this app:** The Dashboard shows advancing vs declining sector counts. Open the Dashboard or ask me *"Which sectors are up today?"* to see live breadth data.`,
    related: ["dashboard", "sector-rotation", "volume", "market-phase"],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Suggestion categories
// ─────────────────────────────────────────────────────────────────────────────
const CATEGORIES = [
  {
    label: "App Features",
    icon: "🗂️",
    questions: [
      { q: "What does the Dashboard show?",      id: "dashboard" },
      { q: "How do I use Chart Studio?",          id: "chart-studio" },
      { q: "What is the Stock Lookup page?",      id: "stock-lookup" },
      { q: "What are the Patterns?",              id: "patterns-page" },
      { q: "What are the Scanners?",              id: "scanners-page" },
      { q: "What is the Insights page?",          id: "insights-page" },
      { q: "What is the Options Tester?",         id: "options-tester" },
    ],
  },
  {
    label: "AI & Bots",
    icon: "🤖",
    questions: [
      { q: "What is the AI Stock Analyst?",       id: "ai-stock-analyst" },
      { q: "What is the Investor Council?",       id: "investor-council" },
      { q: "What is Hydra Alpha?",                id: "ai-analyzer" },
      { q: "How accurate is the AI Analyst?",     id: "ai-track-record" },
      { q: "How does the Telegram Bot work?",     id: "telegram-bot" },
      { q: "How does the WhatsApp Bot work?",     id: "whatsapp-bot" },
      { q: "How do I set up price alerts?",       id: "bot-alerts" },
    ],
  },
  {
    label: "Your Portfolio",
    icon: "💼",
    questions: [
      { q: "What does the Portfolio page do?",    id: "portfolio" },
      { q: "Can I connect my brokerage account?", id: "connect-broker" },
      { q: "What is the Daily Email Digest?",     id: "email-digest" },
      { q: "What is DCF Valuation?",              id: "dcf-valuation" },
      { q: "What is Tri-Factor Scoring?",         id: "tri-factor-scoring" },
    ],
  },
  {
    label: "Macro & News",
    icon: "🌏",
    questions: [
      { q: "What is the Macro Pulse?",            id: "macro-pulse" },
      { q: "What are FII / DII flows?",           id: "fii-dii" },
      { q: "What is the News Feed?",              id: "news-feed" },
      { q: "What is the Sentiment Dashboard?",    id: "sentiment-dashboard" },
    ],
  },
  {
    label: "Market Basics",
    icon: "📚",
    questions: [
      { q: "What is the stock market?",           id: "stock-market" },
      { q: "What is NIFTY 50?",                   id: "nifty" },
      { q: "What is a sector?",                   id: "what-sector" },
      { q: "What is market cap?",                 id: "market-cap" },
      { q: "How do I start investing?",           id: "how-to-invest" },
    ],
  },
  {
    label: "Technical Analysis",
    icon: "📊",
    questions: [
      { q: "What is RSI?",                        id: "rsi" },
      { q: "What is MACD?",                       id: "macd" },
      { q: "What are moving averages?",           id: "moving-averages" },
      { q: "What are candlestick patterns?",      id: "candlestick" },
      { q: "What is support and resistance?",     id: "support-resistance" },
      { q: "What is a volume spike?",             id: "volume" },
    ],
  },
  {
    label: "Options & Strategies",
    icon: "📐",
    questions: [
      { q: "What are call and put options?",      id: "call-put" },
      { q: "What are the Options Greeks?",        id: "greeks" },
      { q: "What is implied volatility?",         id: "iv" },
      { q: "What is an Iron Condor?",             id: "iron-condor" },
      { q: "What is a Straddle?",                 id: "straddle" },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Knowledge base lookup
// ─────────────────────────────────────────────────────────────────────────────
// Normalise: lowercase, strip punctuation, collapse whitespace.
function _norm(s: string): string {
  return s.toLowerCase().replace(/[^\w\s/&]/g, " ").replace(/\s+/g, " ").trim();
}

// Tokenise into words, filtering very short stop-words.
const STOP = new Set([
  "the", "a", "an", "is", "are", "of", "for", "to", "in", "on", "at",
  "what", "how", "why", "when", "do", "does", "i", "me", "my", "and",
  "or", "but", "with", "about", "this", "that", "it", "its",
]);
function _tokens(s: string): string[] {
  return _norm(s).split(/\s+|\//).filter(t => t && !STOP.has(t));
}

// Levenshtein distance — small/cheap, used only for short single-word checks.
function _dist(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const m = a.length, n = b.length;
  const prev = new Array(n + 1).fill(0);
  const cur = new Array(n + 1).fill(0);
  for (let j = 0; j <= n; j++) prev[j] = j;
  for (let i = 1; i <= m; i++) {
    cur[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    for (let j = 0; j <= n; j++) prev[j] = cur[j];
  }
  return prev[n];
}

// Check if any query token is "close enough" to any keyword token.
function _tokenMatches(qTokens: string[], kwTokens: string[]): number {
  let hits = 0;
  for (const kt of kwTokens) {
    for (const qt of qTokens) {
      if (qt === kt) { hits++; break; }
      // partial / typo tolerance for words >= 4 chars
      if (kt.length >= 4 && qt.length >= 4) {
        if (qt.startsWith(kt) || kt.startsWith(qt) ||
            qt.endsWith(kt)   || kt.endsWith(qt)) {
          hits += 0.8;
          break;
        }
        const tol = kt.length >= 6 ? 2 : 1;
        if (_dist(qt, kt) <= tol) { hits += 0.6; break; }
      }
    }
  }
  return hits;
}

function findAnswer(question: string): { entry: Entry | null; score: number; suggestions: Entry[] } {
  const qNorm = _norm(question);
  const qTokens = _tokens(question);
  if (!qTokens.length) return { entry: null, score: 0, suggestions: [] };

  type Scored = { entry: Entry; score: number };
  const scored: Scored[] = [];

  for (const entry of KB) {
    let score = 0;

    // Phrase-substring match (existing behaviour, hardened with word boundaries
    // for short keywords so e.g. "ad" doesn't match inside "dashboard").
    for (const kw of entry.keywords) {
      const k = kw.toLowerCase();
      const hasShortToken = k.split(/\s+|\//).some(t => t.length > 0 && t.length < 4);
      if (hasShortToken) {
        // Require word-boundary match
        const escaped = k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const re = new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`);
        if (re.test(qNorm)) score += k.split(" ").length * 3;
      } else {
        if (qNorm.includes(k)) score += k.split(" ").length * 3;
      }
    }

    // Token-level matching (new) — covers typos, partial words
    for (const kw of entry.keywords) {
      const kwTokens = _tokens(kw);
      if (!kwTokens.length) continue;
      const hits = _tokenMatches(qTokens, kwTokens);
      if (hits > 0) {
        // Reward higher coverage of the keyword's tokens
        const coverage = hits / kwTokens.length;
        score += coverage * (kwTokens.length + 1);
      }
    }

    // Exact title match bonus
    if (qNorm.includes(_norm(entry.title))) score += 12;

    // Title token coverage
    const titleTokens = _tokens(entry.title);
    if (titleTokens.length) {
      const titleHits = _tokenMatches(qTokens, titleTokens);
      score += (titleHits / titleTokens.length) * 2;
    }

    if (score > 0) scored.push({ entry, score });
  }

  scored.sort((a, b) => b.score - a.score);
  const top = scored[0];
  const suggestions = scored.slice(1, 4).map(s => s.entry);

  // Confidence threshold — below this we treat as "no good match".
  // Kept low so typos like "ration" → "ratio" still resolve.
  const CONFIDENT = 2;
  if (!top || top.score < CONFIDENT) {
    return { entry: null, score: top?.score ?? 0, suggestions: scored.slice(0, 3).map(s => s.entry) };
  }
  return { entry: top.entry, score: top.score, suggestions };
}

function getById(id: string) { return KB.find(e => e.id === id) ?? null; }

// ─────────────────────────────────────────────────────────────────────────────
// Markdown-ish renderer for bold and bullet lines
// ─────────────────────────────────────────────────────────────────────────────
function RichText({ text }: { text: string }) {
  return (
    <div className="space-y-1">
      {text.split("\n").map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1" />;

        // Parse inline **bold**
        function renderInline(s: string) {
          return s.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
            p.startsWith("**") && p.endsWith("**")
              ? <strong key={j} className="font-semibold text-gray-900 dark:text-white">{p.slice(2, -2)}</strong>
              : <span key={j}>{p}</span>
          );
        }

        const isHeader = line.startsWith("🌱") || line.startsWith("🚀") || line.startsWith("🌅") ||
          line.startsWith("🐻") || line.startsWith("📗") || line.startsWith("📕") ||
          line.startsWith("🏦") || line.startsWith("📈") || line.startsWith("📉") ||
          line.startsWith("⚖️") || line.startsWith("✅") || line.startsWith("❌") ||
          line.startsWith("⚠️");

        if (line.startsWith("  →") || line.startsWith("  •")) {
          return (
            <div key={i} className="flex gap-2 pl-3 text-[12px] text-gray-600 dark:text-gray-400 leading-relaxed">
              <span className="flex-shrink-0 mt-0.5 opacity-50">›</span>
              <span>{renderInline(line.replace(/^  [→•]\s*/, ""))}</span>
            </div>
          );
        }
        if (line.startsWith("  ")) {
          return (
            <div key={i} className="pl-3 text-[12px] text-gray-600 dark:text-gray-400 leading-relaxed">
              {renderInline(line)}
            </div>
          );
        }

        return (
          <div key={i} className={`text-[13px] leading-relaxed ${isHeader ? "font-medium text-gray-800 dark:text-gray-200" : "text-gray-700 dark:text-gray-300"}`}>
            {renderInline(line)}
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Full-featured markdown renderer for Options AI messages (tables, lists, etc.)
// ─────────────────────────────────────────────────────────────────────────────
function AiRichText({ text }: { text: string }) {
  function parseInline(s: string): React.ReactNode[] {
    const parts: React.ReactNode[] = [];
    const re = /\*\*(.*?)\*\*|`([^`]+)`|\*(.*?)\*/g;
    let last = 0; let m: RegExpExecArray | null;
    while ((m = re.exec(s)) !== null) {
      if (m.index > last) parts.push(s.slice(last, m.index));
      if (m[1] !== undefined)
        parts.push(<strong key={m.index} className="font-semibold text-gray-900 dark:text-white">{m[1]}</strong>);
      else if (m[2] !== undefined)
        parts.push(<code key={m.index} className="bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded-md text-[11px] font-mono border border-indigo-100 dark:border-indigo-700/30">{m[2]}</code>);
      else if (m[3] !== undefined)
        parts.push(<em key={m.index} className="italic text-gray-600 dark:text-gray-400">{m[3]}</em>);
      last = re.lastIndex;
    }
    if (last < s.length) parts.push(s.slice(last));
    return parts;
  }

  type Block =
    | { type: "table"; rows: string[] }
    | { type: "heading"; level: number; text: string }
    | { type: "bullet"; text: string; depth: number }
    | { type: "ordered"; text: string; n: number }
    | { type: "rule" }
    | { type: "blank" }
    | { type: "text"; text: string };

  const lines = text.split("\n");
  const blocks: Block[] = [];

  for (const raw of lines) {
    const line = raw;
    const trimmed = line.trim();

    if (!trimmed) { blocks.push({ type: "blank" }); continue; }

    // Table row
    if (/^\|.+\|/.test(trimmed)) {
      const last = blocks[blocks.length - 1];
      if (last?.type === "table") { last.rows.push(line); }
      else blocks.push({ type: "table", rows: [line] });
      continue;
    }
    // Heading
    const hm = trimmed.match(/^(#{1,3})\s+(.*)/);
    if (hm) { blocks.push({ type: "heading", level: hm[1].length, text: hm[2] }); continue; }
    // HR
    if (/^[-*_]{3,}$/.test(trimmed)) { blocks.push({ type: "rule" }); continue; }
    // Bullet
    const bm = line.match(/^(\s*)[•\-*]\s+(.*)/);
    if (bm) { blocks.push({ type: "bullet", text: bm[2], depth: Math.floor(bm[1].length / 2) }); continue; }
    // Ordered
    const om = trimmed.match(/^(\d+)\.\s+(.*)/);
    if (om) { blocks.push({ type: "ordered", text: om[2], n: Number(om[1]) }); continue; }
    // Normal text
    blocks.push({ type: "text", text: line });
  }

  function renderTable(rows: string[]) {
    const isSep = (r: string) => /^\|[\s|:–-]+\|$/.test(r.trim());
    const parseRow = (r: string) =>
      r.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
    const nonSep = rows.filter(r => !isSep(r));
    if (nonSep.length < 1) return null;
    const [header, ...dataRows] = nonSep;
    const headers = parseRow(header);
    return (
      <div className="my-3 -mx-1 overflow-x-auto rounded-2xl shadow-lg border border-indigo-100 dark:border-indigo-800/40">
        <table className="w-full border-collapse text-[11.5px]" style={{ minWidth: 260 }}>
          <thead>
            <tr style={{ background: "linear-gradient(135deg, #6366f1 0%, #7c3aed 100%)" }}>
              {headers.map((h, hi) => (
                <th key={hi}
                  className={`px-3.5 py-2.5 text-left font-bold text-white tracking-wide whitespace-nowrap
                    ${hi === 0 ? "rounded-tl-2xl" : ""} ${hi === headers.length - 1 ? "rounded-tr-2xl" : ""}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dataRows.map((row, ri) => {
              const cells = parseRow(row);
              return (
                <tr key={ri}
                  className={`border-t border-indigo-50 dark:border-indigo-900/30 transition-colors
                    ${ri % 2 === 0
                      ? "bg-white dark:bg-gray-800"
                      : "bg-indigo-50/40 dark:bg-indigo-900/10"}`}>
                  {cells.map((cell, ci) => (
                    <td key={ci}
                      className={`px-3.5 py-2 leading-snug
                        ${ci === 0
                          ? "font-semibold text-indigo-700 dark:text-indigo-300 whitespace-nowrap"
                          : "text-gray-600 dark:text-gray-300"}`}>
                      {parseInline(cell)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  const headingClass = ["", "text-[14px] font-bold text-gray-900 dark:text-white mt-3 mb-1", "text-[13px] font-semibold text-indigo-700 dark:text-indigo-300 mt-2.5 mb-0.5", "text-[12px] font-semibold text-gray-700 dark:text-gray-300 mt-2"];

  return (
    <div className="space-y-1 text-[12.5px]">
      {blocks.map((block, bi) => {
        if (block.type === "blank")   return <div key={bi} className="h-1.5" />;
        if (block.type === "rule")    return <hr key={bi} className="border-indigo-100 dark:border-indigo-800/40 my-2" />;
        if (block.type === "table")   return <React.Fragment key={bi}>{renderTable(block.rows)}</React.Fragment>;
        if (block.type === "heading") return <p key={bi} className={headingClass[block.level]}>{parseInline(block.text)}</p>;
        if (block.type === "bullet")  return (
          <div key={bi} className={`flex gap-2 items-start ${block.depth > 0 ? "pl-4" : ""}`}>
            <span className={`flex-shrink-0 mt-1 w-1.5 h-1.5 rounded-full ${block.depth === 0 ? "bg-indigo-500" : "bg-gray-400"}`} />
            <span className="leading-relaxed text-gray-700 dark:text-gray-300">{parseInline(block.text)}</span>
          </div>
        );
        if (block.type === "ordered") return (
          <div key={bi} className="flex gap-2 items-start">
            <span className="flex-shrink-0 text-indigo-500 dark:text-indigo-400 font-semibold text-[11px] w-4 text-right mt-0.5">{block.n}.</span>
            <span className="leading-relaxed text-gray-700 dark:text-gray-300">{parseInline(block.text)}</span>
          </div>
        );
        return (
          <p key={bi} className="leading-relaxed text-gray-700 dark:text-gray-300">
            {parseInline(block.text)}
          </p>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────
interface Msg {
  id: string;
  role: "user" | "bot";
  text: string;
  entry?: Entry;
  suggestions?: Entry[];
  loading?: boolean;
  source?: "kb" | "ai" | "fallback";
}

let _msgSeq = 0;
function _newMsgId(): string {
  _msgSeq += 1;
  return `m_${Date.now().toString(36)}_${_msgSeq}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────
type AiMsg = { role: "user" | "assistant"; content: string };

export default function GlobalAssistant() {
  const [loc] = useLocation();
  const isChartStudio = loc.startsWith("/trading") || loc.startsWith("/chart");
  const isOptions = loc.startsWith("/options");

  const [open, setOpen]           = useState(false);
  const [msgs, setMsgs]           = useState<Msg[]>([]);
  const [input, setInput]         = useState("");
  const [activeCategory, setActive] = useState<string | null>(null);
  const [showHint, setShowHint]   = useState(false);
  const [tabHovered, setTabHovered] = useState(false);
  const endRef   = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Options AI chat state
  const [aiMode, setAiMode]       = useState(false);
  const [aiMsgs, setAiMsgs]       = useState<AiMsg[]>([]);
  const [aiInput, setAiInput]     = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const aiEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  useEffect(() => { aiEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [aiMsgs]);
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 150); }, [open]);

  // Switch back to Learn mode when leaving the options page
  useEffect(() => { if (!isOptions) setAiMode(false); }, [isOptions]);

  async function sendAiChat() {
    const text = aiInput.trim();
    if (!text || aiLoading) return;
    const userMsg: AiMsg = { role: "user", content: text };
    setAiMsgs(prev => [...prev, userMsg]);
    setAiInput("");
    setAiLoading(true);
    try {
      const reply = await optionsChat([...aiMsgs, userMsg]);
      setAiMsgs(prev => [...prev, { role: "assistant", content: reply }]);
    } catch {
      setAiMsgs(prev => [...prev, {
        role: "assistant",
        content: "Sorry, couldn't reach the AI right now. Please try again.",
      }]);
    } finally {
      setAiLoading(false);
    }
  }

  // First-visit hint — slide out the tooltip after 1.2 s, retract after 5 s
  useEffect(() => {
    if (localStorage.getItem("learn-hint-shown")) return;
    const t1 = setTimeout(() => setShowHint(true), 1200);
    const t2 = setTimeout(() => {
      setShowHint(false);
      localStorage.setItem("learn-hint-shown", "1");
    }, 5200);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  // Close on Escape
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); setTabHovered(false); } };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  async function ask(question: string, entryId?: string) {
    const q = question.trim();
    if (!q) return;

    // Direct ID-based ask (from clickable suggestions)
    if (entryId) {
      const entry = getById(entryId);
      setMsgs(prev => [
        ...prev,
        { id: _newMsgId(), role: "user", text: q },
        { id: _newMsgId(), role: "bot", text: entry?.answer ?? "Topic not found.", entry: entry ?? undefined, source: "kb" },
      ]);
      setInput("");
      return;
    }

    // KB lookup with confidence
    const { entry, suggestions } = findAnswer(q);
    setInput("");

    if (entry) {
      setMsgs(prev => [
        ...prev,
        { id: _newMsgId(), role: "user", text: q },
        { id: _newMsgId(), role: "bot", text: entry.answer, entry, source: "kb" },
      ]);
      return;
    }

    // No good match — show typing indicator and ask the backend assistant
    const placeholderId = _newMsgId();
    setMsgs(prev => [
      ...prev,
      { id: _newMsgId(), role: "user", text: q },
      { id: placeholderId, role: "bot", text: "", loading: true, source: "ai" },
    ]);

    const aiReply = await smartFallback(q);

    setMsgs(prev => prev.map(m => {
      if (m.id !== placeholderId) return m;
      if (aiReply) {
        return { ...m, text: aiReply, loading: false, source: "ai", suggestions };
      }
      const hint = suggestions.length
        ? `I couldn't find a perfect match for "${q}". Did you mean one of these?`
        : `I don't have an answer for "${q}" yet. Try rephrasing — for example: *"What is RSI?"*, *"How does the Dashboard work?"*, or *"What is an Iron Condor?"*\n\nYou can also browse topics using the category buttons above.`;
      return { ...m, text: hint, loading: false, source: "fallback", suggestions };
    }));
  }

  function handleRelated(id: string) {
    const e = getById(id);
    if (!e) return;
    setMsgs(prev => [
      ...prev,
      { id: _newMsgId(), role: "user", text: e.title },
      { id: _newMsgId(), role: "bot", text: e.answer, entry: e, source: "kb" },
    ]);
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") { e.preventDefault(); ask(input); }
  }

  const isEmpty = msgs.length === 0;

  // Hide entirely on Chart Studio — it has its own toolset and the tab would block controls
  if (isChartStudio) return null;

  return (
    <>
      {/* ══════════════════════════════════════════════════════════════════════
          PEEK TAB — right-edge, auto-hidden, visible when panel is closed
         ══════════════════════════════════════════════════════════════════════ */}
      {!open && (
        <div
          className="fixed z-[9999] flex items-center pointer-events-none"
          style={{ right: 0, top: "50%", transform: "translateY(-50%)" }}
        >
          {/* First-visit tooltip — slides in from the tab */}
          <div
            className="flex items-center gap-2 mr-1.5 pointer-events-none"
            style={{
              opacity: showHint ? 1 : 0,
              transform: showHint ? "translateX(0)" : "translateX(12px)",
              transition: "opacity 0.4s ease, transform 0.4s ease",
            }}
          >
            <div className="
              bg-indigo-600 text-white text-xs font-semibold
              px-3 py-2 rounded-lg shadow-xl whitespace-nowrap
              flex items-center gap-1.5
            ">
              <GraduationCap className="w-3.5 h-3.5" />
              Learn market concepts
              <span className="text-white/60">→</span>
            </div>
            {/* Small arrow pointing right toward the tab */}
            <div className="w-0 h-0"
              style={{
                borderTop: "5px solid transparent",
                borderBottom: "5px solid transparent",
                borderLeft: "6px solid #4f46e5",
              }}
            />
          </div>

          {/* The peek tab */}
          <button
            onClick={() => { setOpen(true); setShowHint(false); setTabHovered(false); }}
            onMouseEnter={() => setTabHovered(true)}
            onMouseLeave={() => setTabHovered(false)}
            aria-label="Open learning assistant"
            className="pointer-events-auto"
            style={{
              borderRadius: "10px 0 0 10px",
              width: tabHovered ? 44 : 28,
              height: tabHovered ? 112 : 96,
              transition: "width 0.25s ease, height 0.25s ease, box-shadow 0.25s ease",
              boxShadow: tabHovered
                ? "-8px 0 32px rgba(99,102,241,0.6)"
                : "-4px 0 20px rgba(99,102,241,0.35)",
              background: "linear-gradient(180deg, #6366f1 0%, #4f46e5 50%, #7c3aed 100%)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              cursor: "pointer",
              border: "none",
              outline: "none",
              flexShrink: 0,
            }}
          >
            <GraduationCap
              style={{
                width: 13,
                height: 13,
                color: "white",
                flexShrink: 0,
                opacity: tabHovered ? 1 : 0.9,
                transition: "opacity 0.2s",
              }}
            />
            <span
              style={{
                writingMode: "vertical-rl",
                transform: "rotate(180deg)",
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: "0.12em",
                color: "white",
                textTransform: "uppercase",
                lineHeight: 1,
                opacity: tabHovered ? 1 : 0.85,
                transition: "opacity 0.2s",
              }}
            >
              Learn
            </span>
            <ChevronLeft
              style={{
                width: 11,
                height: 11,
                color: "rgba(255,255,255,0.7)",
                flexShrink: 0,
                transform: tabHovered ? "translateX(-2px)" : "none",
                transition: "transform 0.2s ease",
              }}
            />
          </button>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          BACKDROP + DRAWER — visible when panel is open
         ══════════════════════════════════════════════════════════════════════ */}
      {open && (
        <>
          <div
            className="fixed inset-0 z-[9997] bg-black/30 backdrop-blur-[2px]"
            onClick={() => { setOpen(false); setTabHovered(false); }}
            aria-hidden
          />

          {/* Right-side drawer */}
          <div className="
            fixed inset-y-0 right-0 z-[9998]
            w-[420px] max-w-[100vw]
            flex flex-col
            bg-white dark:bg-gray-900
            border-l border-gray-200 dark:border-white/[0.07]
            shadow-[-24px_0_60px_rgba(0,0,0,0.18)]
            dark:shadow-[-24px_0_60px_rgba(0,0,0,0.55)]
            overflow-hidden
          ">
          {/* Header — gradient glass */}
          <div
            className="flex items-center gap-3 px-4 py-3.5 flex-shrink-0 relative overflow-hidden"
            style={{ background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 60%, #6366f1 100%)" }}
          >
            {/* Subtle noise texture overlay */}
            <div className="absolute inset-0 opacity-[0.07]"
              style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='%23fff' fill-opacity='1'%3E%3Cpath d='M0 0h1v1H0zm2 0h1v1H2zm2 0h1v1H4zm2 0h1v1H6zm2 0h1v1H8zm2 0h1v1h-1zm2 0h1v1h-1zm2 0h1v1h-1zm2 0h1v1h-1zm2 0h1v1h-1z'/%3E%3C/g%3E%3C/svg%3E\")" }}
            />
            {/* Soft glow blob */}
            <div className="absolute -top-4 -right-4 w-20 h-20 rounded-full bg-violet-400/30 blur-2xl pointer-events-none" />

            <div className="w-8 h-8 rounded-lg bg-white/15 backdrop-blur-sm border border-white/20 flex items-center justify-center flex-shrink-0 relative">
              <GraduationCap className="w-4 h-4 text-white" />
            </div>
            <div className="flex-1 min-w-0 relative">
              <p className="text-white font-semibold text-[13px] leading-tight tracking-wide">Market Learning Assistant</p>
              <p className="text-white/60 text-[10px] leading-tight mt-0.5">
                Concepts · App features · In plain English
              </p>
            </div>
            <div className="flex items-center gap-0.5 relative">
              {msgs.length > 0 && (
                <button
                  onClick={() => { setMsgs([]); setActive(null); }}
                  title="Start over"
                  className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/15 transition"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              )}
              <button
                onClick={() => { setOpen(false); setTabHovered(false); }}
                title="Close"
                className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/15 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Mode toggle — only on /options page */}
          {isOptions && (
            <div className="flex-shrink-0 flex border-b border-gray-200 dark:border-white/[0.08] bg-white dark:bg-gray-900">
              <button
                onClick={() => setAiMode(false)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[12px] font-semibold transition border-b-2
                  ${!aiMode
                    ? "border-indigo-600 text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-900/20"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"}`}
              >
                <BookOpen className="w-3.5 h-3.5" />
                Learn
              </button>
              <button
                onClick={() => setAiMode(true)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[12px] font-semibold transition border-b-2
                  ${aiMode
                    ? "border-indigo-600 text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-900/20"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"}`}
              >
                <Bot className="w-3.5 h-3.5" />
                Options AI
              </button>
            </div>
          )}

          {/* AI chat body — visible when in AI mode */}
          {aiMode && (
            <>
              {/* Messages area */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0
                bg-gradient-to-b from-indigo-50/60 via-violet-50/40 to-purple-50/60
                dark:from-[#0d0b1e] dark:via-[#100e2a] dark:to-[#0f0c24]">
                {aiMsgs.length === 0 && (
                  <div className="flex flex-col items-center pt-6 pb-4 px-2">
                    {/* Glowing orb */}
                    <div className="relative mb-5">
                      <div className="absolute inset-0 rounded-3xl bg-violet-500/30 blur-xl scale-150" />
                      <div className="relative w-[68px] h-[68px] rounded-3xl flex items-center justify-center shadow-xl"
                        style={{ background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 60%, #a855f7 100%)" }}>
                        <Bot className="w-8 h-8 text-white drop-shadow" />
                      </div>
                    </div>
                    <p className="text-[15px] font-bold text-gray-800 dark:text-white">Options AI</p>
                    <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-1 text-center leading-relaxed max-w-[250px]">
                      Ask about Greeks, strategies, IV, or your current position
                    </p>

                    {/* Prompt chips */}
                    <div className="mt-5 w-full space-y-2">
                      <p className="text-[9.5px] font-black text-indigo-300 uppercase tracking-[0.15em] text-center mb-3">Try asking</p>
                      {[
                        { q: "What is an Iron Condor?",                     icon: "📐" },
                        { q: "Explain Delta and Gamma",                     icon: "🔢" },
                        { q: "Best NIFTY strategy for range-bound market?", icon: "📊" },
                        { q: "What is Implied Volatility?",                 icon: "📈" },
                      ].map(({ q, icon }) => (
                        <button key={q} onClick={() => setAiInput(q)}
                          className="w-full flex items-center gap-3 text-left rounded-2xl px-4 py-3 transition-all group
                            border border-indigo-100 dark:border-indigo-800/40
                            bg-white/80 dark:bg-white/5
                            hover:bg-indigo-50 dark:hover:bg-indigo-900/30
                            hover:border-indigo-300 dark:hover:border-indigo-600
                            hover:shadow-sm backdrop-blur-sm">
                          <span className="text-[18px] leading-none">{icon}</span>
                          <span className="text-[12px] text-gray-600 dark:text-gray-300 group-hover:text-indigo-700 dark:group-hover:text-indigo-300 leading-snug font-medium">{q}</span>
                          <ChevronRight className="ml-auto w-3.5 h-3.5 text-gray-300 dark:text-gray-600 group-hover:text-indigo-400 transition flex-shrink-0" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {aiMsgs.map((m, i) => (
                  <div key={i} className={`flex gap-2.5 ${m.role === "user" ? "justify-end" : "justify-start"} items-end`}>

                    {/* AI avatar */}
                    {m.role === "assistant" && (
                      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-md mb-0.5">
                        <Bot style={{ width: 13, height: 13 }} className="text-white" />
                      </div>
                    )}

                    {m.role === "user" ? (
                      /* ── User bubble ── */
                      <div className="max-w-[78%] bg-gradient-to-br from-indigo-600 to-violet-600 text-white rounded-2xl rounded-br-md px-4 py-2.5 shadow-md text-[13px] leading-relaxed">
                        {m.content}
                      </div>
                    ) : (
                      /* ── AI card — wide, allows table overflow ── */
                      <div className="flex-1 min-w-0 overflow-hidden rounded-2xl rounded-bl-md shadow-md
                        border border-indigo-100/80 dark:border-indigo-700/30
                        bg-gradient-to-br from-white to-violet-50/60
                        dark:from-[#1e1b4b] dark:to-[#1a1035]">
                        <div className="px-4 pt-3 pb-3.5 overflow-x-auto">
                          <AiRichText text={m.content} />
                        </div>
                      </div>
                    )}

                    {/* User avatar */}
                    {m.role === "user" && (
                      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center mb-0.5 shadow-sm">
                        <span className="text-[9px] font-black text-white tracking-tight">YOU</span>
                      </div>
                    )}
                  </div>
                ))}
                {aiLoading && (
                  <div className="flex gap-2.5 items-end">
                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-md mb-0.5">
                      <Bot style={{ width: 13, height: 13 }} className="text-white" />
                    </div>
                    <div className="rounded-2xl rounded-bl-md border border-indigo-100/80 dark:border-indigo-700/30 px-5 py-3.5 shadow-md
                      bg-gradient-to-br from-white to-violet-50/60 dark:from-[#1e1b4b] dark:to-[#1a1035]">
                      <div className="flex gap-1.5 items-center">
                        <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                        <span className="w-2 h-2 rounded-full bg-violet-400 animate-bounce" style={{ animationDelay: "160ms" }} />
                        <span className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "320ms" }} />
                      </div>
                    </div>
                  </div>
                )}
                <div ref={aiEndRef} />
              </div>

              {/* Input bar */}
              <div className="flex-shrink-0 border-t border-indigo-100/60 dark:border-indigo-700/40 px-3 py-3
                bg-gradient-to-r from-violet-50 to-indigo-50 dark:from-[#0d0b1e] dark:to-[#110e28]">
                <div className="flex items-center gap-2 rounded-2xl border border-indigo-200/70 dark:border-indigo-500/50 px-3.5 py-2.5
                  bg-white dark:bg-gray-800 shadow-sm
                  focus-within:border-indigo-400 dark:focus-within:border-indigo-400
                  focus-within:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] transition-all">
                  <input
                    type="text"
                    value={aiInput}
                    onChange={e => setAiInput(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), sendAiChat())}
                    placeholder="Ask about options, Greeks, strategies…"
                    className="flex-1 text-[13px] bg-transparent text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none min-w-0"
                  />
                  <button
                    onClick={sendAiChat}
                    disabled={!aiInput.trim() || aiLoading}
                    className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all
                      bg-indigo-600 hover:bg-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-400
                      disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Send className="w-3.5 h-3.5 text-white" />
                  </button>
                </div>
                <p className="text-[10px] text-center text-indigo-400 dark:text-indigo-400 mt-2">
                  AI-powered · Options &amp; derivatives focused
                </p>
              </div>
            </>
          )}

          {/* Learn panel — hidden in AI mode */}
          {!aiMode && (<>
          <div className="flex-shrink-0 border-b border-gray-100 dark:border-white/[0.06] bg-gray-50 dark:bg-gray-800/50 px-3 py-2 overflow-x-auto">
            <div className="flex gap-1.5" style={{ width: "max-content" }}>
              {CATEGORIES.map(cat => (
                <button
                  key={cat.label}
                  onClick={() => setActive(a => a === cat.label ? null : cat.label)}
                  className={`
                    flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full border whitespace-nowrap transition
                    ${activeCategory === cat.label
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-white/10 hover:border-indigo-300 hover:text-indigo-600 dark:hover:text-indigo-400"
                    }
                  `}
                >
                  <span>{cat.icon}</span>
                  <span>{cat.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Category suggestions panel */}
          {activeCategory && (
            <div className="flex-shrink-0 border-b border-gray-100 dark:border-white/[0.06] bg-indigo-50/60 dark:bg-indigo-900/10 px-3 py-2">
              <div className="grid grid-cols-1 gap-1">
                {CATEGORIES.find(c => c.label === activeCategory)?.questions.map(({ q, id }) => (
                  <button
                    key={id}
                    onClick={() => { ask(q, id); setActive(null); }}
                    className="flex items-center justify-between gap-2 text-left text-[12px] px-3 py-1.5 rounded-lg
                      text-indigo-700 dark:text-indigo-300
                      hover:bg-indigo-100 dark:hover:bg-indigo-800/30
                      transition group"
                  >
                    <span>{q}</span>
                    <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 opacity-40 group-hover:opacity-100 transition" />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0 bg-gray-50 dark:bg-gray-950">

            {isEmpty && (
              <div className="flex flex-col items-center text-center py-6 px-4">
                <div className="w-14 h-14 rounded-2xl bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center mb-3">
                  <Sparkles className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
                </div>
                <p className="font-bold text-gray-800 dark:text-white text-sm">
                  Hi! I'm your Market Guide 👋
                </p>
                <p className="text-gray-500 dark:text-gray-400 text-xs mt-1.5 leading-relaxed">
                  I explain stock market concepts and every feature in this app — in simple, plain language. No jargon, no confusion.
                </p>
                <div className="mt-4 flex flex-col gap-1.5 w-full text-left">
                  {[
                    { q: "What does the Dashboard show?",    id: "dashboard" },
                    { q: "What is RSI?",                     id: "rsi" },
                    { q: "How do I use Chart Studio?",       id: "chart-studio" },
                    { q: "What are candlestick patterns?",   id: "candlestick" },
                    { q: "What is sector rotation?",         id: "sector-rotation" },
                  ].map(({ q, id }) => (
                    <button
                      key={id}
                      onClick={() => ask(q, id)}
                      className="flex items-center justify-between gap-2 text-left text-xs px-3 py-2 rounded-xl
                        bg-white dark:bg-gray-800
                        border border-gray-200 dark:border-white/10
                        text-gray-700 dark:text-gray-300
                        hover:bg-indigo-50 dark:hover:bg-indigo-900/30
                        hover:text-indigo-700 dark:hover:text-indigo-300
                        hover:border-indigo-200 dark:hover:border-indigo-600
                        transition group"
                    >
                      <span>{q}</span>
                      <ChevronRight className="w-3 h-3 flex-shrink-0 opacity-30 group-hover:opacity-100" />
                    </button>
                  ))}
                </div>
                <p className="text-[11px] text-gray-400 dark:text-gray-600 mt-3">
                  Or pick a category above ↑
                </p>
              </div>
            )}

            {msgs.map((m) => (
              <div key={m.id} className={`flex gap-2.5 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "bot" && (
                  <div className="w-7 h-7 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <BookOpen className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
                  </div>
                )}

                <div className={`max-w-[86%] ${m.role === "user" ? "items-end" : "items-start"} flex flex-col gap-2`}>
                  {/* Bubble */}
                  <div className={`
                    rounded-2xl px-3.5 py-2.5
                    ${m.role === "user"
                      ? "bg-indigo-600 text-white text-[13px] leading-relaxed rounded-tr-sm"
                      : "bg-white dark:bg-gray-800 rounded-tl-sm border border-gray-100 dark:border-white/10 shadow-sm"
                    }
                  `}>
                    {m.role === "user"
                      ? <p>{m.text}</p>
                      : m.loading
                        ? (
                          <div className="flex items-center gap-1.5 py-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" />
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "120ms" }} />
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "240ms" }} />
                            <span className="text-[11px] text-gray-500 dark:text-gray-400 ml-1">Looking that up…</span>
                          </div>
                        )
                        : (
                        <>
                          {m.entry && (
                            <p className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 mb-2 uppercase tracking-wide">
                              {m.entry.title}
                            </p>
                          )}
                          {m.source === "ai"
                            ? <AiRichText text={m.text} />
                            : <RichText text={m.text} />}
                          {m.source === "ai" && (
                            <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 italic">
                              Live answer · powered by the in-app assistant
                            </p>
                          )}
                        </>
                      )
                    }
                  </div>

                  {/* Related topics */}
                  {m.role === "bot" && !m.loading && m.entry?.related && m.entry.related.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      <span className="text-[10px] text-gray-400 dark:text-gray-600 self-center">Related:</span>
                      {m.entry.related.slice(0, 4).map(id => {
                        const rel = getById(id);
                        if (!rel) return null;
                        return (
                          <button
                            key={id}
                            onClick={() => handleRelated(id)}
                            className="text-[11px] px-2 py-0.5 rounded-full
                              bg-indigo-50 dark:bg-indigo-900/30
                              text-indigo-600 dark:text-indigo-400
                              border border-indigo-200 dark:border-indigo-700/50
                              hover:bg-indigo-100 dark:hover:bg-indigo-800/40
                              transition"
                          >
                            {rel.title.replace("What is ", "").replace("What are ", "").replace("How do I use ", "")}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* "Did you mean" suggestions for low-confidence / fallback replies */}
                  {m.role === "bot" && !m.loading && m.suggestions && m.suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      <span className="text-[10px] text-gray-400 dark:text-gray-600 self-center">Did you mean:</span>
                      {m.suggestions.slice(0, 3).map(s => (
                        <button
                          key={s.id}
                          onClick={() => handleRelated(s.id)}
                          className="text-[11px] px-2 py-0.5 rounded-full
                            bg-amber-50 dark:bg-amber-900/20
                            text-amber-700 dark:text-amber-300
                            border border-amber-200 dark:border-amber-700/40
                            hover:bg-amber-100 dark:hover:bg-amber-800/30
                            transition"
                        >
                          {s.title.replace("What is ", "").replace("What are ", "").replace("How do I use ", "")}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>

          {/* Input */}
          <div className="flex-shrink-0 p-3 border-t border-gray-100 dark:border-white/[0.06] bg-white dark:bg-gray-900">
            <div className="flex items-center gap-2 bg-gray-100 dark:bg-gray-800 rounded-xl px-3.5 py-2 border border-gray-200 dark:border-white/10 focus-within:border-indigo-400 dark:focus-within:border-indigo-500 transition">
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKey}
                placeholder="Ask about any market concept or feature…"
                className="flex-1 bg-transparent text-[13px] text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 outline-none min-w-0"
              />
              <button
                onClick={() => ask(input)}
                disabled={!input.trim()}
                className="w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0 transition"
              >
                <Send className="w-3.5 h-3.5 text-white" />
              </button>
            </div>
          </div>
          </>)}
        </div>
        </>
      )}
    </>
  );
}
