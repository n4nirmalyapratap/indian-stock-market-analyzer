---
name: NSE CM Equity Bhav Copy URL format
description: Correct URL pattern for NSE CM UDiFF bhavcopy downloads (post July 8, 2024)
---

Correct URL (works from Replit/cloud):
  https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip

**Why:** The `_0000` suffix is required — exactly parallel to the F&O format (`BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip`). Without it NSE returns HTTP 404. Multiple web sources document the format incorrectly, omitting `_0000`.

**How to apply:** Any time you build or read from nse_equity_bhavcopy_service.py, confirm the URL uses `_0000`. The date is in `YYYYMMDD` format (e.g. `20260630`).

Real CSV columns (UDiFF): TckrSymb, SctySrs, BizDt, OpnPric, HghPric, LwPric, ClsPric, TtlTradgVol
Filter: SctySrs == 'EQ' for main-board equities only.
