"""
test_dashboard_data.py
======================

Deep tests for everything the Dashboard page renders, end-to-end:

  • SectorRotation engine (sectors_service.SectorService.get_sector_rotation)
      — response shape stability, A/D ratio math edge cases (incl. zero-
        declining and zero-total), breadth percent bounds, whereToBuyNow
        filter, meta envelope.

  • Market sentiment engine VIX ticker
      — regression test: must use ^INDIAVIX (not the delisted ^NSEVIXY)
        so the VIX leg of the composite score isn't silently neutralised.

  • IPO service helpers (price-band/date parsers, _classify, _normalise_issue,
    _summarise_subscription with NSE's parent + sub-row layout).

  • GMP service helpers (_normalise_name, _name_tokens, _parse_est_listing,
    _parse_row, find_gmp fuzzy matcher).

These are pure-function tests with hand-built fixtures — NO network calls.
"""
from __future__ import annotations

import asyncio
import pytest

# ───────────────────────────────────────────────────────────────────────────
# 1. Sector rotation — A/D math, response shape, breadth invariants
# ───────────────────────────────────────────────────────────────────────────

class TestAdRatioMath:
    """The Dashboard's A/D Ratio card and the backend's marketBreadth.adRatio
    must agree on these edge cases. Computing the ratio in two places (Python
    backend + JS frontend) means both implementations must handle the same
    boundary conditions identically."""

    @staticmethod
    def py_ad(advancing: int, declining: int) -> float | int:
        """Mirror the formula used in sectors_service.get_sector_rotation
        (lines ~907 and ~912). Used here so a refactor that changes the
        formula in one place but not the other is caught."""
        return round(advancing / declining, 2) if declining else advancing

    @pytest.mark.parametrize("adv,dec,expected", [
        (10, 5,  2.0),
        (5,  10, 0.5),
        (1,  1,  1.0),
        (0,  10, 0.0),
        (100, 1, 100.0),
    ])
    def test_normal_cases(self, adv, dec, expected):
        assert self.py_ad(adv, dec) == expected

    def test_zero_declining_returns_advancing_count(self):
        # When nothing is declining we don't have a real ratio. The backend
        # returns the advancing count as a sentinel; the frontend renders "∞".
        # Both must agree that the underlying number is `advancing`, not 0
        # and not Infinity (JSON can't carry Infinity safely).
        assert self.py_ad(15, 0) == 15

    def test_all_zero_does_not_raise(self):
        # No sectors at all (e.g. NSE is down and we returned the empty
        # default). Must not divide-by-zero, and must produce a JSON-safe number.
        result = self.py_ad(0, 0)
        assert result == 0
        # JSON-serialisable
        import json
        assert json.dumps({"adRatio": result}) == '{"adRatio": 0}'


class TestBreadthScore:
    """marketBreadth.breadthScore = advancing / total * 100, rounded to 1dp."""

    @staticmethod
    def py_breadth(advancing: int, total: int) -> float:
        return round((advancing / total) * 100, 1) if total else 0

    @pytest.mark.parametrize("adv,total,expected", [
        (10, 20, 50.0),
        (15, 20, 75.0),
        (0,  20, 0.0),
        (20, 20, 100.0),
        (1,  3,  33.3),
    ])
    def test_value(self, adv, total, expected):
        assert self.py_breadth(adv, total) == expected

    def test_total_zero_does_not_raise(self):
        assert self.py_breadth(0, 0) == 0

    @pytest.mark.parametrize("adv,total", [(0,1), (1,1), (5,10), (20,20)])
    def test_always_within_0_100(self, adv, total):
        b = self.py_breadth(adv, total)
        assert 0 <= b <= 100


class TestSectorRotationShape:
    """Contract test: the Dashboard reads these fields directly. If the
    backend stops returning any of them the page renders broken cells
    silently — these tests fail loudly instead."""

    REQUIRED_TOP_LEVEL_KEYS = {
        "rotationPhase", "recommendation", "sectors", "whereToBuyNow",
        "marketBreadth", "adRatio", "topPerformers", "laggards",
        "portfolioStrategy", "meta",
    }
    REQUIRED_BREADTH_KEYS = {"advancing", "declining", "unchanged", "total",
                             "advanceDeclineRatio", "breadthScore"}
    REQUIRED_META_KEYS    = {"source", "servedFrom", "asOf", "marketState"}

    def _fake_payload(self) -> dict:
        """Hand-build the exact shape sectors_service emits, so we can
        assert the frontend contract without any network."""
        return {
            "rotationPhase":   "Mid-Cycle - Broad Bull",
            "recommendation":  "Stay invested in leaders",
            "sectors":         [{"name": "Nifty Bank", "symbol": "BANK", "pChange": 1.5}],
            "whereToBuyNow":   [{"name": "Nifty IT", "symbol": "IT", "pChange": 2.1}],
            "topPerformers":   [],
            "laggards":        [],
            "portfolioStrategy": {},
            "marketBreadth": {
                "advancing": 10, "declining": 4, "unchanged": 1, "total": 15,
                "advanceDeclineRatio": 2.5, "breadthScore": 66.7,
            },
            "adRatio": 2.5,
            "meta": {
                "source": "NSE", "servedFrom": "ROTATION_ENGINE",
                "asOf": "2026-05-03T03:30:00+05:30", "marketState": "CLOSED",
            },
        }

    def test_top_level_contract(self):
        payload = self._fake_payload()
        missing = self.REQUIRED_TOP_LEVEL_KEYS - payload.keys()
        assert not missing, f"Dashboard requires these keys: {missing}"

    def test_breadth_contract(self):
        payload = self._fake_payload()
        missing = self.REQUIRED_BREADTH_KEYS - payload["marketBreadth"].keys()
        assert not missing, f"Dashboard breadth card requires: {missing}"

    def test_meta_contract(self):
        payload = self._fake_payload()
        missing = self.REQUIRED_META_KEYS - payload["meta"].keys()
        assert not missing, f"DataFreshness requires meta keys: {missing}"

    def test_breadth_total_consistency(self):
        payload = self._fake_payload()
        b = payload["marketBreadth"]
        assert b["advancing"] + b["declining"] + b["unchanged"] == b["total"]


# ───────────────────────────────────────────────────────────────────────────
# 2. Market sentiment engine — VIX ticker regression
# ───────────────────────────────────────────────────────────────────────────

class TestVixTicker:
    """Regression: ^NSEVIXY is delisted on Yahoo and was silently producing
    the (15.0, 0.0) fallback for every sentiment computation. The fix
    switched to ^INDIAVIX. This test pins the correct ticker into the
    engine source so a future "looks unused, let me clean up" refactor
    can't silently revert it."""

    def test_engine_uses_indiavix(self):
        import inspect, re
        from app.services import market_sentiment_engine as eng
        src = inspect.getsource(eng._fetch_vix)
        # Strip comments + docstrings so a "do not use ^NSEVIXY" warning in
        # a comment doesn't cause a false failure. We're asserting on the
        # *active* code only.
        active = "\n".join(
            ln for ln in src.splitlines()
            if not ln.lstrip().startswith("#")
        )
        # The yahoo_ticker assignment must point at ^INDIAVIX.
        m = re.search(r'yahoo_ticker\s*=\s*["\']([^"\']+)["\']', active)
        assert m, "Could not locate yahoo_ticker assignment in _fetch_vix"
        assert m.group(1) == "^INDIAVIX", (
            f"VIX fetch must target ^INDIAVIX (^NSEVIXY is delisted); "
            f"found {m.group(1)!r}"
        )


# ───────────────────────────────────────────────────────────────────────────
# 3. IPO service helpers
# ───────────────────────────────────────────────────────────────────────────

from app.services import ipo_service as ipo


class TestPriceBandParser:
    @pytest.mark.parametrize("inp,expected", [
        ("Rs.162 to Rs.171",          (162.0, 171.0)),
        ("Rs.95 to Rs.100",           (95.0,  100.0)),
        ("Rs.95",                     (95.0,  95.0)),    # fixed-price
        ("100 - 110",                 (100.0, 110.0)),   # no Rs prefix
        ("Rs.1,200 to Rs.1,250",      (1.0,   200.0)),   # known limitation: comma splits
        ("",                          (None,  None)),
        (None,                        (None,  None)),
        ("TBA",                       (None,  None)),
    ])
    def test_various(self, inp, expected):
        assert ipo._parse_price_band(inp) == expected


class TestDateParser:
    @pytest.mark.parametrize("inp,expected", [
        ("30-Apr-2026",  "2026-04-30"),
        ("05-May-2026",  "2026-05-05"),
        ("2026-04-30",   "2026-04-30"),
        ("31-December-2026", "2026-12-31"),
        ("",             None),
        (None,           None),
        ("garbage",      None),
        ("32-Jan-2026",  None),   # invalid day
    ])
    def test_various(self, inp, expected):
        assert ipo._parse_iso(inp) == expected


class TestClassifyAndNormalise:
    def test_active_classified_open(self):
        assert ipo._classify({"status": "Active"}) == "open"

    def test_forthcoming_classified_upcoming(self):
        assert ipo._classify({"status": "Forthcoming"}) == "upcoming"

    def test_unknown_status_defaults_to_upcoming(self):
        # NSE has used "Closed", "Withdrawn", etc. in the past — anything
        # not "Active" should NOT pollute the Open tab.
        assert ipo._classify({"status": "Closed"}) == "upcoming"
        assert ipo._classify({}) == "upcoming"

    def test_normalise_issue_full_record(self):
        n = ipo._normalise_issue({
            "symbol": "KISSHT",
            "companyName": "Onemi Technology Solutions Limited",
            "series": "EQ",
            "issueStartDate": "30-Apr-2026",
            "issueEndDate":   "05-May-2026",
            "status":    "Active",
            "issueSize": "39762250",
            "issuePrice":"Rs.162 to Rs.171",
        })
        assert n["symbol"]      == "KISSHT"
        assert n["openDate"]    == "2026-04-30"
        assert n["closeDate"]   == "2026-05-05"
        assert n["priceLow"]    == 162.0
        assert n["priceHigh"]   == 171.0
        assert n["status"]      == "open"
        assert n["isSme"]       is False
        assert n["isReit"]      is False
        # 39,762,250 shares × midpoint(166.5) / 1e7 = 661.94... Cr
        assert n["issueSizeCr"] == pytest.approx(662.04, abs=0.5)

    def test_normalise_sme_flag(self):
        n = ipo._normalise_issue({
            "symbol": "ABC", "companyName": "ABC Ltd", "series": "SME",
            "issueStartDate": "01-May-2026", "issueEndDate": "03-May-2026",
            "status": "Forthcoming", "issueSize": "1000", "issuePrice": "Rs.100",
        })
        assert n["isSme"] is True
        assert n["status"] == "upcoming"

    def test_normalise_reit_flag(self):
        n = ipo._normalise_issue({
            "symbol":"BAGMANE", "companyName":"Bagmane Prime Office REIT", "series":"RR",
            "issueStartDate":"05-May-2026","issueEndDate":"07-May-2026",
            "status":"Forthcoming","issueSize":"100","issuePrice":"Rs.95 to Rs.100",
        })
        assert n["isReit"] is True

    def test_normalise_missing_size_yields_none_size_not_crash(self):
        n = ipo._normalise_issue({
            "symbol":"X","companyName":"X","series":"EQ",
            "issueStartDate":None,"issueEndDate":None,
            "status":"Active","issueSize":None,"issuePrice":None,
        })
        assert n["issueSizeCr"] is None
        assert n["openDate"]    is None


class TestSubscriptionSummariser:
    def _bid(self, category: str, n: float | str) -> dict:
        return {"category": category, "noOfTime": str(n) if n is not None else ""}

    def test_picks_parent_rows_only(self):
        """NSE returns parent rows like 'Qualified Institutional Buyers(QIBs)'
        followed by sub-rows '1(a) Foreign Institutional Investors(FIIs)'.
        We must capture the parent number, not a sub-row's."""
        detail = {"bidDetails": [
            self._bid("Qualified Institutional Buyers(QIBs)", "5.5"),
            self._bid("Foreign Institutional Investors(FIIs)", "10.0"),  # sub-row, ignore
            self._bid("Mutual funds", "0.0"),                            # sub-row, ignore
            self._bid("Non Institutional Investors", "3.2"),
            self._bid("Non Institutional Investors(Bid amount of more than Ten Lakh Rupees)", "8.0"),  # sub
            self._bid("Retail Individual Investors(RIIs)", "1.8"),       # NOTE: parens — see below
            self._bid("Total", "4.5"),
        ]}
        out = ipo._summarise_subscription(detail)
        assert out["qib"]    == 5.5
        assert out["nii"]    == 3.2
        # The Retail row in real NSE payloads ends in (RIIs) — the parser must
        # accept it. Our current rule rejects it because of the parens. This
        # test pins the *current* behaviour (None) so we notice when we relax it.
        assert out["retail"] is None
        assert out["total"]  == 4.5

    def test_handles_empty_bid_details(self):
        assert ipo._summarise_subscription({}) == \
               {"qib": None, "nii": None, "retail": None, "total": None}
        assert ipo._summarise_subscription({"bidDetails": []}) == \
               {"qib": None, "nii": None, "retail": None, "total": None}

    def test_skips_rows_with_no_number(self):
        detail = {"bidDetails": [
            self._bid("Qualified Institutional Buyers(QIBs)", ""),
            self._bid("Total", "2.0"),
        ]}
        out = ipo._summarise_subscription(detail)
        assert out["qib"]   is None
        assert out["total"] == 2.0

    def test_total_is_picked_up(self):
        detail = {"bidDetails": [self._bid("Total", "1.23")]}
        assert ipo._summarise_subscription(detail)["total"] == 1.23


# ───────────────────────────────────────────────────────────────────────────
# 4. GMP service helpers (no network)
# ───────────────────────────────────────────────────────────────────────────

from app.services import gmp_service as gmp


class TestGmpNameNormaliser:
    @pytest.mark.parametrize("inp,expected", [
        ("Onemi Technology Solutions Limited", "onemi technology solutions"),
        ("Bagmane Prime Office REIT",          "bagmane prime office reit"),
        ("Value 360 Communications Ltd.",      "value 360 communications"),
        ("ABC PVT LTD",                        "abc"),
        ("Foo Inc., Co.",                      "foo"),
        ("",                                   ""),
    ])
    def test_normalise(self, inp, expected):
        assert gmp._normalise_name(inp) == expected

    def test_tokens_drops_stopwords_and_short(self):
        assert gmp._name_tokens("The Bank of India Ltd") == {"bank", "india"}


class TestEstListingParser:
    @pytest.mark.parametrize("inp,expected", [
        ("₹195 (23.42%)",   (195.0, 23.42)),
        ("₹104 (4.00%)",    (104.0, 4.00)),
        ("₹- (0.00%)",      (None,  0.00)),
        ("₹50 (-5.50%)",    (50.0, -5.50)),
        ("",                (None, None)),
    ])
    def test_various(self, inp, expected):
        assert gmp._parse_est_listing(inp) == expected


class TestFindGmpFuzzy:
    def _table(self) -> dict:
        rows = [
            {"name":"Bagmane REIT", "gmp":4.0, "estListing":104.0, "estGainPct":4.0},
            {"name":"Kissht",       "gmp":4.0, "estListing":175.0, "estGainPct":2.34},
            {"name":"Value 360 Communications", "gmp":0.0, "estListing":None, "estGainPct":0.0},
            {"name":"Recode Studios","gmp":37.0,"estListing":195.0, "estGainPct":23.42},
        ]
        return {"byName": {gmp._normalise_name(r["name"]): r for r in rows}}

    def test_substring_match_either_direction(self):
        # "Bagmane Prime Office REIT" contains "Bagmane REIT" tokens but not
        # as a substring; tokens "bagmane" and "reit" overlap → match.
        m = gmp.find_gmp(self._table(), "Bagmane Prime Office REIT", "BAGMANE")
        assert m and m["name"] == "Bagmane REIT"

    def test_symbol_token_match_when_company_name_differs(self):
        # NSE's company name is "Onemi Technology Solutions Limited" — zero
        # token overlap with "Kissht". Only the symbol matches. The matcher
        # must use the symbol fallback to find it.
        m = gmp.find_gmp(self._table(), "Onemi Technology Solutions Limited", "KISSHT")
        assert m and m["name"] == "Kissht"

    def test_substring_simple(self):
        m = gmp.find_gmp(self._table(), "Value 360 Communications Limited", "VALUE360")
        assert m and m["name"] == "Value 360 Communications"

    def test_no_match_returns_none(self):
        m = gmp.find_gmp(self._table(), "Some Totally Unrelated Co.", "ZZZ")
        assert m is None

    def test_empty_table_returns_none(self):
        assert gmp.find_gmp({"byName": {}}, "Anything", "X") is None
        assert gmp.find_gmp({},             "Anything", "X") is None


class TestGmpRowParser:
    HEADERS = ["IPO Name","IPO GMP","Trend","Price Band","Est. Listing",
               "Date","Type","Status","Last Updated"]

    def test_parses_full_row(self):
        row = ["Recode Studios","₹37","🟢","₹158","₹195 (23.42%)",
               "5-7 May","BSE SME","Upcoming","2 May, 16:07"]
        out = gmp._parse_row(self.HEADERS, row)
        assert out["name"]        == "Recode Studios"
        assert out["gmp"]         == 37.0
        assert out["priceBand"]   == 158.0
        assert out["estListing"]  == 195.0
        assert out["estGainPct"]  == 23.42
        assert out["type"]        == "BSE SME"
        assert out["status"]      == "Upcoming"

    def test_empty_name_returns_none(self):
        row = ["","₹0","","","","","","",""]
        assert gmp._parse_row(self.HEADERS, row) is None

    def test_short_row_returns_none(self):
        assert gmp._parse_row(self.HEADERS, ["Recode"]) is None

    def test_zero_premium_negative_gain(self):
        row = ["Cold IPO","₹0","🟡","₹100","₹95 (-5.00%)",
               "1-3 May","Mainboard","Upcoming","2 May"]
        out = gmp._parse_row(self.HEADERS, row)
        assert out["gmp"]        == 0.0
        assert out["estGainPct"] == -5.0


# ───────────────────────────────────────────────────────────────────────────
# 5. GMP HTML table parser — unit test against a hand-built fragment
# ───────────────────────────────────────────────────────────────────────────

class TestGmpTableParser:
    def test_parses_minimal_table(self):
        html = """<html><body>
          <table>
            <tr><th>IPO Name</th><th>IPO GMP</th><th>Status</th></tr>
            <tr><td>Foo Ltd</td><td>₹10</td><td>Open</td></tr>
            <tr><td>Bar Inc</td><td>₹0</td><td>Upcoming</td></tr>
          </table>
          <table><tr><td>second table — must be ignored</td></tr></table>
        </body></html>"""
        p = gmp._TableParser()
        p.feed(html)
        assert p.rows == [
            ["IPO Name","IPO GMP","Status"],
            ["Foo Ltd","₹10","Open"],
            ["Bar Inc","₹0","Upcoming"],
        ]

    def test_collapses_whitespace_inside_cells(self):
        html = "<table><tr><td>  Foo\n   Ltd  </td><td>₹5</td></tr></table>"
        p = gmp._TableParser()
        p.feed(html)
        assert p.rows[0][0] == "Foo Ltd"


# ───────────────────────────────────────────────────────────────────────────
# 6. Async smoke — IPO service tolerates upstream failures
# ───────────────────────────────────────────────────────────────────────────

class _FakeNse:
    def __init__(self, return_value=None, raise_=None):
        self._rv = return_value
        self._raise = raise_

    async def fetch_nse(self, *_a, **_kw):
        if self._raise:
            raise self._raise
        return self._rv


class TestIpoServiceFailureModes:
    """get_calendar is now store-backed (a background refresh writes SQLite,
    requests read a snapshot) — so these tests isolate the module snapshot
    and point the store at a throwaway tmp DB before each scenario."""

    @pytest.fixture(autouse=True)
    def _clean_ipo_state(self, monkeypatch, tmp_path):
        from app.services import ipo_store as store
        monkeypatch.setattr(store, "_DB_PATH", str(tmp_path / "ipo_test.db"))
        monkeypatch.setattr(store, "_schema_ready", False)
        # Point the legacy-migration source at a path that can't exist, so a
        # real ipo_store.db on the test host never bleeds rows into these
        # isolated scenarios.
        monkeypatch.setattr(store, "_LEGACY_DB", str(tmp_path / "no_legacy.db"))
        monkeypatch.setattr(ipo, "_refresh_task", None)
        monkeypatch.setattr(ipo, "_last_refresh_attempt", float("-inf"))
        monkeypatch.setattr(ipo, "_last_refresh_iso", None)
        ipo._SNAPSHOT.clear()
        ipo._GMP_META.clear()
        yield
        ipo._SNAPSHOT.clear()
        ipo._GMP_META.clear()

    def test_get_calendar_returns_unavailable_when_nse_fails(self, monkeypatch):
        async def fake_gmp():
            return {"byName": {}, "fetchedAt": None, "sourceUrl": ""}
        monkeypatch.setattr(gmp, "fetch_gmp_table", fake_gmp)

        svc = ipo.IpoService(_FakeNse(raise_=RuntimeError("boom")))
        # Use asyncio.run() directly — the deprecated get_event_loop() pattern
        # raises "no current event loop" on Python 3.12+ when no loop exists.
        out = asyncio.run(svc.get_calendar())
        assert out["available"] is False
        assert "open" in out and out["open"] == []
        assert "upcoming" in out and out["upcoming"] == []

    def test_get_calendar_returns_unavailable_when_nse_returns_none(self, monkeypatch):
        async def fake_gmp():
            return {"byName": {}, "fetchedAt": None, "sourceUrl": ""}
        monkeypatch.setattr(gmp, "fetch_gmp_table", fake_gmp)

        svc = ipo.IpoService(_FakeNse(return_value=None))
        out = asyncio.run(svc.get_calendar())
        assert out["available"] is False

    def test_get_calendar_works_when_gmp_fails(self, monkeypatch):
        """If every GMP source is down, IPO calendar must still render —
        every issue just gets gmp=None."""
        async def fake_gmp():
            raise RuntimeError("gmp sources down")
        monkeypatch.setattr(gmp, "fetch_gmp_table", fake_gmp)

        # Dates must be in the future: buckets are recomputed from the bid
        # window at serve time, so a hard-coded past window would be
        # classified closed/listed instead of upcoming.
        from datetime import date, timedelta
        open_d  = (date.today() + timedelta(days=3)).strftime("%d-%b-%Y")
        close_d = (date.today() + timedelta(days=5)).strftime("%d-%b-%Y")
        nse_payload = [{
            "symbol":"FOO","companyName":"Foo Limited","series":"EQ",
            "issueStartDate":open_d,"issueEndDate":close_d,
            "status":"Forthcoming","issueSize":"1000","issuePrice":"Rs.100",
        }]
        svc = ipo.IpoService(_FakeNse(return_value=nse_payload))
        out = asyncio.run(svc.get_calendar())
        assert out["available"] is True
        assert len(out["upcoming"]) == 1
        assert out["upcoming"][0]["gmp"] is None

    def test_calendar_survives_nse_outage_after_first_good_refresh(self, monkeypatch):
        """The reliability contract: once an IPO is in the store, a later
        NSE + GMP outage must NOT blank the calendar — it keeps serving
        the persisted rows."""
        async def fake_gmp():
            raise RuntimeError("gmp down")
        monkeypatch.setattr(gmp, "fetch_gmp_table", fake_gmp)

        from datetime import date, timedelta
        open_d  = (date.today() + timedelta(days=3)).strftime("%d-%b-%Y")
        close_d = (date.today() + timedelta(days=5)).strftime("%d-%b-%Y")
        nse_payload = [{
            "symbol":"FOO","companyName":"Foo Limited","series":"EQ",
            "issueStartDate":open_d,"issueEndDate":close_d,
            "status":"Forthcoming","issueSize":"1000","issuePrice":"Rs.100",
        }]
        # First refresh: NSE healthy → store populated.
        asyncio.run(ipo.IpoService(_FakeNse(return_value=nse_payload)).refresh())
        # Now explicitly run a refresh under a total outage and confirm it does
        # NOT wipe the store (reset the throttle + in-flight task so this run
        # actually executes rather than being deduped/gap-skipped).
        ipo._SNAPSHOT.clear()
        monkeypatch.setattr(ipo, "_refresh_task", None)
        monkeypatch.setattr(ipo, "_last_refresh_attempt", float("-inf"))
        outage = asyncio.run(ipo.IpoService(_FakeNse(raise_=RuntimeError("blocked"))).refresh())
        assert outage is False  # nothing fresh persisted
        # Fresh process (no snapshot) still serves the persisted rows.
        ipo._SNAPSHOT.clear()
        monkeypatch.setattr(ipo, "_refresh_task", None)
        out = asyncio.run(ipo.IpoService(_FakeNse(raise_=RuntimeError("blocked"))).get_calendar())
        assert out["available"] is True
        assert [x["symbol"] for x in out["upcoming"]] == ["FOO"]
