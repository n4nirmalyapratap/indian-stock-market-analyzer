import { useState, useRef, useEffect } from "react";
import { BookOpen, Send, X, ChevronDown, RotateCcw, Sparkles, ChevronRight, GraduationCap } from "lucide-react";

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
🤖 **AI Analyzer** — ask market questions in plain English
📐 **Options Tester** — build and test options strategies

Everything connects to live NSE/BSE data. No subscriptions, no charges.`,
    related: ["dashboard", "chart-studio", "sectors-page", "stock-lookup", "patterns-page", "scanners-page", "ai-analyzer", "options-tester"],
  },

  // ── App Features ─────────────────────────────────────────────────────────
  {
    id: "dashboard",
    title: "What does the Dashboard show?",
    keywords: ["dashboard", "home", "market phase", "overview", "main page", "rotation phase", "advancing", "declining", "breadth", "where to buy", "sector rotation"],
    answer: `The **Dashboard** is your market command centre — the first thing you see when you open the app.

**What it shows:**

📍 **Market Phase** — the overall health of the market right now:
  • *Early Bull* → market starting to rise
  • *Full Bull* → strong uptrend
  • *Late Cycle / Slowdown* → market topping out
  • *Bear Market* → market in a downtrend

📈 **Advancing / Declining** — how many sectors are going up vs down today

🎯 **Where to Buy Now** — sectors with the strongest momentum (green bars = positive, red = negative)

🕯️ **Pattern Signals** — stocks showing bullish or bearish candlestick patterns right now

📊 **Sector Rotation Analysis** — a paragraph explaining what the market is doing and what to consider doing

**How to use it:** Check the Dashboard each morning before markets open to get a feel for the day. The Market Phase and "Where to Buy" section tell you where momentum is strongest.`,
    related: ["sector-rotation", "market-phase", "sectors-page"],
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
    keywords: ["stock lookup", "lookup", "search stock", "find stock", "analyze stock", "stock detail", "stock search"],
    answer: `**Stock Lookup** lets you search and analyze any NSE-listed stock in detail.

**What you get when you search a stock:**

💰 **Live price** — current price, day high/low, 52-week high/low

📊 **Technical Analysis:**
  • RSI — is it overbought or oversold?
  • MACD — what's the trend signal?
  • EMA 20 / EMA 50 — is price above or below the average?
  • Support and Resistance levels — where might it bounce or get stuck?

🎯 **Entry Signal** — a suggestion (BUY / SELL / HOLD) based on the technical indicators

📈 **Price chart** — recent price history at a glance

**How to use it:**
1. Type a stock name or symbol (e.g. "Reliance", "TCS", "HDFCBANK")
2. Click Search or press Enter
3. The full analysis appears instantly

**Covered stocks:** Nifty 100, Midcap 150, Smallcap 250, and more — over 500 NSE stocks.

**Tip:** Look for stocks where RSI is between 40–60 AND price is above the 50-day EMA AND MACD is bullish. That's a strong setup.`,
    related: ["rsi", "macd", "moving-averages", "entry-signal"],
  },
  {
    id: "patterns-page",
    title: "What is the Patterns page?",
    keywords: ["patterns", "candlestick pattern", "pattern page", "bullish pattern", "bearish pattern", "call signal", "put signal", "hammer", "doji", "engulfing"],
    answer: `The **Patterns** page automatically scans hundreds of NSE stocks and finds candlestick patterns — visual signals that often predict the next price move.

**How it works:**
The system analyses recent candles for each stock every day. When a recognisable pattern forms, it shows up here.

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
    keywords: ["scanner", "scanners", "screener", "stock screen", "filter stocks", "golden cross", "volume spike", "momentum", "breakout", "oversold"],
    answer: `The **Scanners** page lets you filter the entire NSE market to find stocks matching specific technical criteria — automatically.

**Think of it like this:** Instead of manually checking 500 stocks, the scanner does it for you in seconds.

**Available scanners:**

🏆 **Golden Cross** — finds stocks where the 50-day average has crossed above the 200-day average. This is one of the most powerful long-term buy signals.

📊 **Momentum** — finds stocks with strong, consistent price momentum. Good for trend-following.

📈 **Volume Spike** — finds stocks where today's trading volume is much higher than usual. Big volume often signals a breakout or major event.

🎯 **Oversold Bounce** — finds stocks that have fallen a lot (RSI below 30) and might be due for a bounce upward.

📉 **Breakout** — finds stocks breaking above a key resistance level for the first time.

**How to use it:**
1. Click any scanner card to run it
2. It scans hundreds of stocks in real time
3. Results show the matching stocks with price and percentage change
4. Click any result to open it in Stock Lookup for more detail

**Tip:** The Golden Cross scanner gives the most reliable signals. But always confirm with the Patterns page before acting.`,
    related: ["golden-cross", "moving-averages", "rsi", "volume"],
  },
  {
    id: "ai-analyzer",
    title: "What is the AI Analyzer (Hydra)?",
    keywords: ["ai analyzer", "hydra", "nlp", "natural language", "ask question", "query", "hydra alpha"],
    answer: `The **AI Analyzer** (also called Hydra Alpha) lets you ask market questions in plain English — and get real data back.

**Examples of what you can ask:**
  • "Analyze RELIANCE" → gets full technical analysis
  • "Which sectors are up?" → shows today's sector performance
  • "Show bullish patterns" → lists all bullish candlestick signals
  • "Where should I invest today?" → shows sector rotation data
  • "Run golden cross scanner" → executes the scanner

**How it works:**
It uses a rule-based NLP (Natural Language Processing) engine to understand your question, figure out what you're asking for, and pull the right data from the market.

**No AI costs — it's all rule-based:**
There's no OpenAI or any paid AI behind it. It uses keyword matching and an intent recognition system to route your question to the right data source.

**Best for:** Users who prefer typing questions naturally rather than clicking through menus. It's like a search engine for the app.

**Tip:** You can combine concepts — "Show me bearish stocks in the banking sector" or "Which IT stocks are showing bullish patterns?"`,
    related: ["stock-lookup", "sectors-page", "patterns-page", "scanners-page"],
  },
  {
    id: "options-tester",
    title: "What is the Options Tester?",
    keywords: ["options tester", "options", "strategy tester", "iron condor", "straddle", "strangle", "call option", "put option", "legs", "greeks", "payoff", "options strategy"],
    answer: `The **Options Tester** is a full options strategy builder and analyser — without needing a live brokerage account.

**What you can do:**

🏗️ **Build any options strategy** by adding "legs":
  • Each leg = a call or put option, with a strike price, premium, and lots
  • You can build multi-leg strategies like straddles, iron condors, butterfly spreads, etc.

📐 **Analyse the strategy** to get:
  • **Payoff chart** — shows profit/loss at every possible price at expiry
  • **Max profit** and **max loss**
  • **Breakeven points** — where you start making or losing money
  • **Greeks** (Delta, Gamma, Theta, Vega, Rho)

⚡ **Preset strategies** — click to instantly load:
  Long Call, Long Put, Short Straddle, Iron Condor, Bull Call Spread, Butterfly, and more

🤖 **Built-in AI Chat** — the Options page has its own assistant that explains Greeks, strategies, and your specific position in plain English

🎯 **Risk Analysis** tab — Value at Risk (VaR), scenario analysis (how your trade performs under different price/volatility shocks)

**How to use it:**
1. Type a symbol (e.g. NIFTY, BANKNIFTY, RELIANCE) and click "Fetch Spot"
2. Add legs using the Quick Strategy buttons or manually
3. Click "Analyse Strategy"
4. Study the payoff chart and numbers
5. Ask the chat assistant to explain anything`,
    related: ["call-put", "greeks", "iv", "iron-condor", "straddle"],
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
];

// ─────────────────────────────────────────────────────────────────────────────
// Suggestion categories
// ─────────────────────────────────────────────────────────────────────────────
const CATEGORIES = [
  {
    label: "App Features",
    icon: "🗂️",
    questions: [
      { q: "What does the Dashboard show?",    id: "dashboard" },
      { q: "How do I use Chart Studio?",        id: "chart-studio" },
      { q: "What is the Stock Lookup page?",    id: "stock-lookup" },
      { q: "What are the Patterns?",            id: "patterns-page" },
      { q: "What are the Scanners?",            id: "scanners-page" },
      { q: "What is the Options Tester?",       id: "options-tester" },
    ],
  },
  {
    label: "Market Basics",
    icon: "📚",
    questions: [
      { q: "What is the stock market?",         id: "stock-market" },
      { q: "What is NIFTY 50?",                 id: "nifty" },
      { q: "What is a sector?",                 id: "what-sector" },
      { q: "What is market cap?",               id: "market-cap" },
      { q: "How do I start investing?",         id: "how-to-invest" },
    ],
  },
  {
    label: "Technical Analysis",
    icon: "📊",
    questions: [
      { q: "What is RSI?",                      id: "rsi" },
      { q: "What is MACD?",                     id: "macd" },
      { q: "What are moving averages?",         id: "moving-averages" },
      { q: "What are candlestick patterns?",    id: "candlestick" },
      { q: "What is support and resistance?",   id: "support-resistance" },
      { q: "What is a volume spike?",           id: "volume" },
    ],
  },
  {
    label: "Options & Strategies",
    icon: "📐",
    questions: [
      { q: "What are call and put options?",    id: "call-put" },
      { q: "What are the Options Greeks?",      id: "greeks" },
      { q: "What is implied volatility?",       id: "iv" },
      { q: "What is an Iron Condor?",           id: "iron-condor" },
      { q: "What is a Straddle?",               id: "straddle" },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Knowledge base lookup
// ─────────────────────────────────────────────────────────────────────────────
function findAnswer(question: string): Entry | null {
  const q = question.toLowerCase();
  let best: Entry | null = null;
  let bestScore = 0;

  for (const entry of KB) {
    let score = 0;
    for (const kw of entry.keywords) {
      if (q.includes(kw)) score += kw.split(" ").length * 2; // longer match = more points
    }
    // Exact title match bonus
    if (q.includes(entry.title.toLowerCase())) score += 10;
    if (score > bestScore) { bestScore = score; best = entry; }
  }

  return bestScore > 0 ? best : null;
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
// Types
// ─────────────────────────────────────────────────────────────────────────────
interface Msg {
  role: "user" | "bot";
  text: string;
  entry?: Entry;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────
export default function GlobalAssistant() {
  const [open, setOpen]           = useState(false);
  const [msgs, setMsgs]           = useState<Msg[]>([]);
  const [input, setInput]         = useState("");
  const [activeCategory, setActive] = useState<string | null>(null);
  const endRef   = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 150); }, [open]);

  function ask(question: string, entryId?: string) {
    const q = question.trim();
    if (!q) return;
    const entry = entryId ? getById(entryId) : findAnswer(q);
    const botText = entry
      ? entry.answer
      : "I don't have a specific answer for that yet, but you can try rephrasing — for example: \"What is RSI?\", \"How does the Dashboard work?\", or \"What is an Iron Condor?\"\n\nYou can also browse topics using the category buttons above.";

    setMsgs(prev => [
      ...prev,
      { role: "user", text: q },
      { role: "bot", text: botText, entry: entry ?? undefined },
    ]);
    setInput("");
  }

  function handleRelated(id: string) {
    const e = getById(id);
    if (!e) return;
    setMsgs(prev => [
      ...prev,
      { role: "user", text: e.title },
      { role: "bot", text: e.answer, entry: e },
    ]);
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") { e.preventDefault(); ask(input); }
  }

  const isEmpty = msgs.length === 0;

  return (
    <>
      {/* ── Floating button ─────────────────────────────────────────────────── */}
      <div className="fixed bottom-5 right-5 z-[9999] flex flex-col items-end gap-2">

        {/* Glow ring — only when closed */}
        {!open && (
          <span className="absolute inset-0 rounded-full animate-ping opacity-20 bg-indigo-400 pointer-events-none" style={{ animationDuration: "2.5s" }} />
        )}

        <button
          aria-label="Open learning assistant"
          onClick={() => setOpen(o => !o)}
          className={`
            relative flex items-center gap-2.5
            rounded-full
            transition-all duration-300 ease-out
            select-none
            ${open
              ? "h-10 w-10 justify-center backdrop-blur-xl bg-white/10 dark:bg-white/10 border border-white/20 dark:border-white/15 shadow-lg hover:bg-white/20 dark:hover:bg-white/15"
              : `h-11 pl-4 pr-5
                 backdrop-blur-xl
                 bg-white/15 dark:bg-white/10
                 hover:bg-white/25 dark:hover:bg-white/18
                 border border-white/30 dark:border-white/20
                 hover:border-white/50 dark:hover:border-white/35
                 shadow-[0_8px_32px_rgba(99,102,241,0.35)]
                 hover:shadow-[0_8px_40px_rgba(99,102,241,0.55)]
                 hover:scale-105 active:scale-95`
            }
          `}
        >
          {open ? (
            <X className="w-4 h-4 text-white/80" />
          ) : (
            <>
              {/* Gradient icon container */}
              <div className="w-5 h-5 rounded-full bg-gradient-to-br from-indigo-400 to-violet-500 flex items-center justify-center flex-shrink-0 shadow-sm">
                <GraduationCap className="w-3 h-3 text-white" />
              </div>
              <span className="text-white/90 text-[13px] font-semibold tracking-wide whitespace-nowrap" style={{ letterSpacing: "0.02em" }}>
                Learn
              </span>
              {/* Subtle sparkle dot */}
              <Sparkles className="w-3 h-3 text-indigo-300/60 dark:text-indigo-200/50" />
            </>
          )}
        </button>
      </div>

      {/* ── Chat panel ──────────────────────────────────────────────────────── */}
      {open && (
        <div className="
          fixed bottom-[68px] right-5 z-[9998]
          w-[380px] sm:w-[420px]
          max-h-[calc(100vh-108px)]
          flex flex-col
          backdrop-blur-2xl
          bg-white/80 dark:bg-gray-900/85
          border border-white/40 dark:border-white/10
          rounded-2xl
          shadow-[0_24px_60px_rgba(0,0,0,0.22),0_0_0_1px_rgba(255,255,255,0.08)]
          dark:shadow-[0_24px_60px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.05)]
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
                onClick={() => setOpen(false)}
                title="Close"
                className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/15 transition"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Category tabs */}
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

            {msgs.map((m, i) => (
              <div key={i} className={`flex gap-2.5 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
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
                      : (
                        <>
                          {m.entry && (
                            <p className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 mb-2 uppercase tracking-wide">
                              {m.entry.title}
                            </p>
                          )}
                          <RichText text={m.text} />
                        </>
                      )
                    }
                  </div>

                  {/* Related topics */}
                  {m.role === "bot" && m.entry?.related && m.entry.related.length > 0 && (
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
        </div>
      )}
    </>
  );
}
