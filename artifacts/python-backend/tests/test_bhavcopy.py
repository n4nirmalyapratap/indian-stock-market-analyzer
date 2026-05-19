"""
test_bhavcopy.py — NSE/BSE F&O bhavcopy parsing, caching and lookup.

We never hit the live NSE archive in tests; everything is built from
in-memory CSV bytes.  An isolated SQLite DB is created per test via the
NSE_BHAVCOPY_DB env var so the production cache is never touched.
"""

from __future__ import annotations

import importlib
import io
import os
import zipfile
from datetime import date

import pytest


@pytest.fixture
def bhav(tmp_path, monkeypatch):
    """Return a freshly-imported bhavcopy module pointing at an isolated DB."""
    db_path = tmp_path / "test_options.sqlite"
    monkeypatch.setenv("NSE_BHAVCOPY_DB", str(db_path))
    # Reimport the module so the module-level _DB_PATH constant is rebuilt.
    import app.services.nse_bhavcopy_service as m
    importlib.reload(m)
    return m


# ── CSV fixtures ────────────────────────────────────────────────────────────

LEGACY_CSV = (
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP\n"
    "OPTIDX,NIFTY,28-MAR-2024,22000,CE,150.00,180.00,140.00,165.50,165.50,12000,1234.50,500000,1000,15-MAR-2024\n"
    "OPTIDX,NIFTY,28-MAR-2024,22000,PE,120.00,140.00,100.00,110.25,110.25,11000,1100.20,400000,500,15-MAR-2024\n"
    "OPTIDX,BANKNIFTY,27-MAR-2024,46000,CE,300.00,350.00,280.00,310.00,310.00,8000,800.00,200000,200,15-MAR-2024\n"
    "FUTIDX,NIFTY,28-MAR-2024,0,XX,22050,22100,22000,22075,22075,1000,500.00,100000,50,15-MAR-2024\n"
)

UDIFF_CSV = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
    "2024-08-01,2024-08-01,FO,NSE,OPTIDX,123,,NIFTY,,2024-08-29,2024-08-29,24500,CE,N1,200,220,180,205.5,205,210,24400,205.5,500000,100,5000,1000.5,200,A,75,,,,,\n"
    "2024-08-01,2024-08-01,FO,NSE,OPTIDX,124,,NIFTY,,2024-08-29,2024-08-29,24500,PE,N2,150,170,140,160.25,160,165,24400,160.25,400000,200,4000,800.0,150,A,75,,,,,\n"
    "2024-08-01,2024-08-01,FO,NSE,FUTIDX,125,,NIFTY,,2024-08-29,2024-08-29,0,XX,N3,24500,24600,24400,24550,24550,24500,24500,24550,100000,50,1500,300.0,100,A,75,,,,,\n"
)


def _zip_csv(name: str, body: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, body)
    return buf.getvalue()


# ── Parsing ─────────────────────────────────────────────────────────────────

class TestParse:
    def test_legacy_filters_to_options_only(self, bhav):
        recs = bhav.parse_bhavcopy(LEGACY_CSV.encode(), date(2024, 3, 15))
        # 3 option rows in the fixture (FUTIDX must be filtered out)
        assert len(recs) == 3
        assert all(r["opt_type"] in ("call", "put") for r in recs)

    def test_legacy_normalizes_symbol_and_expiry(self, bhav):
        recs = bhav.parse_bhavcopy(LEGACY_CSV.encode(), date(2024, 3, 15))
        nifty_call = next(r for r in recs if r["symbol"] == "NIFTY" and r["opt_type"] == "call")
        assert nifty_call["expiry"] == "2024-03-28"
        assert nifty_call["strike"] == 22_000.0
        assert nifty_call["close"] == 165.50
        assert nifty_call["trade_date"] == "2024-03-15"

    def test_udiff_parses(self, bhav):
        recs = bhav.parse_bhavcopy(UDIFF_CSV.encode(), date(2024, 8, 1))
        assert len(recs) == 2          # FUTIDX must be filtered
        nifty_put = next(r for r in recs if r["opt_type"] == "put")
        assert nifty_put["symbol"] == "NIFTY"
        assert nifty_put["expiry"] == "2024-08-29"
        assert nifty_put["strike"] == 24_500.0
        assert nifty_put["close"] == 160.25

    def test_skips_garbage_rows(self, bhav):
        bad = ("INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR\n"
               "OPTIDX,,28-MAR-2024,22000,CE,1,1,1,1,1\n"           # blank symbol
               "OPTIDX,NIFTY,28-MAR-2024,abc,CE,1,1,1,1,1\n"        # bad strike
               "OPTIDX,NIFTY,28-MAR-2024,22000,XX,1,1,1,1,1\n")     # bad opt type
        recs = bhav.parse_bhavcopy(bad.encode(), date(2024, 3, 15))
        assert recs == []


# ── DB ingest + lookup ───────────────────────────────────────────────────────

class TestCache:
    def test_round_trip_legacy(self, bhav):
        recs = bhav.parse_bhavcopy(LEGACY_CSV.encode(), date(2024, 3, 15))
        with bhav._connect() as conn:
            n = bhav._insert_records(conn, recs)
            conn.commit()
        assert n == 3
        px = bhav.lookup_premium("NIFTY", date(2024, 3, 28), 22_000, "call",
                                  date(2024, 3, 15))
        assert px == pytest.approx(165.50)

    def test_lookup_miss_returns_none(self, bhav):
        # Nothing inserted yet
        assert bhav.lookup_premium("NIFTY", date(2024, 3, 28), 22_000, "call",
                                    date(2024, 3, 15)) is None

    def test_lookup_unknown_symbol_short_circuits(self, bhav):
        # Random equity symbol — not in scope for this cache
        assert bhav.lookup_premium("RELIANCE", date(2024, 3, 28), 2900, "call",
                                    date(2024, 3, 15)) is None

    def test_settle_fallback_when_no_close(self, bhav):
        # Untraded option: CLOSE=0 but SETTLE_PR is published
        csv_body = (
            "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP\n"
            "OPTIDX,NIFTY,28-MAR-2024,30000,CE,0,0,0,0,2.50,0,0,1000,0,15-MAR-2024\n"
        )
        recs = bhav.parse_bhavcopy(csv_body.encode(), date(2024, 3, 15))
        with bhav._connect() as conn:
            bhav._insert_records(conn, recs)
            conn.commit()
        px = bhav.lookup_premium("NIFTY", date(2024, 3, 28), 30_000, "call",
                                  date(2024, 3, 15))
        assert px == pytest.approx(2.50)

    def test_coverage_summary(self, bhav):
        recs = bhav.parse_bhavcopy(LEGACY_CSV.encode(), date(2024, 3, 15))
        with bhav._connect() as conn:
            bhav._insert_records(conn, recs)
            conn.commit()
        cov = bhav.get_coverage()
        assert cov["row_count"] == 3
        assert cov["date_min"] == "2024-03-15"
        sym_counts = {r["symbol"]: r["c"] for r in cov["by_symbol"]}
        assert sym_counts["NIFTY"] == 2
        assert sym_counts["BANKNIFTY"] == 1


# ── Download orchestration (network mocked) ─────────────────────────────────

class TestDownload:
    def test_udiff_first_after_cutover(self, bhav, monkeypatch):
        called: list[str] = []
        def fake_get(url, **kw):
            called.append(url)
            if "BhavCopy_NSE_FO" in url:
                return _zip_csv("BhavCopy.csv", UDIFF_CSV)
            return None
        monkeypatch.setattr(bhav, "_http_get", fake_get)
        body, src = bhav.download_bhavcopy(date(2024, 8, 1))
        assert body is not None
        assert src == "nse_udiff"
        assert "BhavCopy_NSE_FO" in called[0]   # tried UDiFF first

    def test_legacy_first_before_cutover(self, bhav, monkeypatch):
        called: list[str] = []
        def fake_get(url, **kw):
            called.append(url)
            if "fo15MAR2024" in url:
                return _zip_csv("fo.csv", LEGACY_CSV)
            return None
        monkeypatch.setattr(bhav, "_http_get", fake_get)
        body, src = bhav.download_bhavcopy(date(2024, 3, 15))
        assert body is not None
        assert src == "nse_legacy"
        assert "fo15MAR2024" in called[0]

    def test_fallback_to_bse(self, bhav, monkeypatch):
        # Both NSE attempts return None → BSE wins
        def fake_get(url, **kw):
            if "bseindia.com" in url:
                return UDIFF_CSV.encode()      # BSE serves plain CSV
            return None
        monkeypatch.setattr(bhav, "_http_get", fake_get)
        body, src = bhav.download_bhavcopy(date(2024, 8, 1))
        assert body is not None
        assert src == "bse_udiff"

    def test_all_sources_fail_returns_empty(self, bhav, monkeypatch):
        monkeypatch.setattr(bhav, "_http_get", lambda url, **kw: None)
        body, src = bhav.download_bhavcopy(date(2024, 3, 15))
        assert body is None
        assert src == ""

    def test_ingest_records_log(self, bhav, monkeypatch):
        monkeypatch.setattr(bhav, "_http_get",
                            lambda url, **kw: _zip_csv("fo.csv", LEGACY_CSV))
        res = bhav.ingest_bhavcopy(date(2024, 3, 15))
        assert res["status"] == "ok"
        assert res["rows"] == 3
        cov = bhav.get_coverage()
        assert any(r["trade_date"] == "2024-03-15" for r in cov["recent_ingests"])


# ── Backtest integration ────────────────────────────────────────────────────

class TestBacktestIntegration:
    """End-to-end checks that the backtester consults bhavcopy and surfaces
    premium_source on every trade record + the aggregate breakdown.  Uses
    a synthetic yfinance mock so no network is touched."""

    def _mock_yf(self, monkeypatch):
        """Return a yf.Ticker stub returning 6 months of fake daily bars."""
        import pandas as pd
        import numpy as np
        idx = pd.date_range("2024-01-01", "2024-06-28", freq="B", tz="Asia/Kolkata")
        rng = np.random.default_rng(42)
        # Mild random walk around 22_000
        prices = 22_000 + np.cumsum(rng.normal(0, 50, len(idx)))
        df = pd.DataFrame({
            "Open": prices, "High": prices + 20, "Low": prices - 20,
            "Close": prices, "Volume": 1_000_000,
        }, index=idx)

        class _T:
            def __init__(self, sym): self.sym = sym
            def history(self, **kw): return df.copy()

        import yfinance as yf
        monkeypatch.setattr(yf, "Ticker", _T)

    def test_synthetic_only_when_cache_empty(self, bhav, monkeypatch):
        """Empty cache → every entry/exit fill must be tagged synthetic_bs;
        every expiry exit must be tagged intrinsic_settlement."""
        import app.services.options_backtest_service as obs
        importlib.reload(obs)
        self._mock_yf(monkeypatch)

        res = obs._run_backtest_sync(
            symbol="NIFTY", strategy="long_call",
            start_date="2024-02-01", end_date="2024-06-15",
            lots=1, lot_size=75, entry_dte=15, roll_dte=0,
            otm_pct=0.03, risk_free=0.07, use_weekly=False,
        )
        assert "trades" in res and len(res["trades"]) >= 2
        psb = res["premium_source_breakdown"]
        # No bhavcopy data is cached, so the real-data ratio must be 0%.
        # Every entry fill is synthetic_bs; exit fills are either synthetic_bs
        # (when exit_ts < expiry) or intrinsic_settlement (when exit_ts == expiry).
        assert psb["bhavcopy_fills"] == 0
        assert psb["real_pct"] == 0.0
        assert psb["synthetic_bs_fills"] >= len(res["trades"])
        assert psb["primary_source"] in ("synthetic_bs", "intrinsic_settlement")
        # Aggregate keys are always present so the UI can render the badge
        assert set(psb).issuperset({
            "bhavcopy_fills", "synthetic_bs_fills",
            "intrinsic_settlement_fills", "real_pct", "synthetic_pct",
            "intrinsic_settlement_pct", "primary_source", "note",
        })

        # Per-trade tagging — every trade carries its own source breakdown
        # and per-leg attribution
        for t in res["trades"]:
            assert t["premium_source"] in ("synthetic_bs", "intrinsic_settlement")
            assert "premium_source_breakdown" in t
            assert "leg_premium_sources" in t
            assert len(t["leg_premium_sources"]) >= 1
            for lps in t["leg_premium_sources"]:
                # Entry must always come from synthetic (cache empty)
                assert lps["entry_premium_source"] == "synthetic_bs"
                # Exit is either synthetic_bs (rolled before expiry) or
                # intrinsic_settlement (settled at expiry) — never bhavcopy
                # because the cache is empty.
                assert lps["exit_premium_source"] in (
                    "synthetic_bs", "intrinsic_settlement"
                )

    def test_real_when_cache_populated(self, bhav, monkeypatch):
        """Pre-seed the cache with NIFTY ATM call/put covering an entry date
        in the backtest range and confirm at least one bhavcopy fill is
        recorded and tagged correctly."""
        import app.services.options_backtest_service as obs
        importlib.reload(obs)
        self._mock_yf(monkeypatch)

        # Seed: cover the 28-MAR-2024 expiry with a wide strike grid so the
        # backtester's ATM strike for that entry date is found.
        seed_rows = []
        for k in range(20_000, 24_001, 100):
            for opt in ("call", "put"):
                seed_rows.append(dict(
                    symbol="NIFTY", trade_date="2024-03-13",
                    expiry="2024-03-28", strike=float(k), opt_type=opt,
                    open=100, high=120, low=80, close=100.0, settle=100.0,
                    contracts=10, oi=100,
                ))
        with bhav._connect() as conn:
            bhav._insert_records(conn, seed_rows)
            conn.commit()

        res = obs._run_backtest_sync(
            symbol="NIFTY", strategy="long_call",
            start_date="2024-03-01", end_date="2024-04-30",
            lots=1, lot_size=75, entry_dte=15, roll_dte=0,
            otm_pct=0.05, risk_free=0.07, use_weekly=False,
        )
        psb = res["premium_source_breakdown"]
        assert psb["bhavcopy_fills"] >= 1, \
            f"Expected >=1 bhavcopy fill, got breakdown {psb}"
        # Find the trade whose entry date is 2024-03-13 (or nearest trading day
        # >= entry_target = 2024-03-13) and check its leg sources include bhavcopy
        bhav_trade = next(
            (t for t in res["trades"]
             if any(l["entry_premium_source"] == "bhavcopy"
                    for l in t["leg_premium_sources"])),
            None,
        )
        assert bhav_trade is not None
        # Aggregate keys present
        assert set(psb).issuperset({
            "bhavcopy_fills", "synthetic_bs_fills",
            "intrinsic_settlement_fills", "real_pct",
            "synthetic_pct", "intrinsic_settlement_pct",
            "primary_source", "note",
        })
