---
name: NSE live API vs archives from cloud IPs
description: What works and what doesn't when accessing NSE from Replit/cloud
---

**NSE live API (www.nseindia.com):** Blocked by Akamai Bot Manager based on datacenter IP reputation. HTTP/2 (h2 package) helps on some cloud providers but NOT on Replit. Circuit breaker handles the 503s cleanly.

**NSE archives (nsearchives.nseindia.com):** No Akamai wall. A browser User-Agent is sufficient. Works perfectly from Replit.

**Why:** nsearchives is a CDN/static asset host; nseindia.com is the main app behind Akamai.

**How to apply:** For historical OHLCV, always prefer the bhav copy archive path over the live NSE API. For live quotes during market hours, use Yahoo/BSE as fallback — they are never Akamai-gated.

Provider chain order in price_service.py:
  UserBroker → NseBhavcopyProvider → NseProvider → BSE → Yahoo → TwelveData → Stooq → HistoryDerived

NseBhavcopyProvider behaviour:
  - Market CLOSED → returns local SQLite bars (primary, fast)
  - Market OPEN   → returns [] so Yahoo serves today's intraday
  - get_quote     → always None
