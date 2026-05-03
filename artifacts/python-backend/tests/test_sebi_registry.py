"""Tests for app.services.sebi_registry — the single source of truth for
SEBI/NSE/BSE rule data used by the Options Strategy Tester.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import sebi_registry as reg


# ─── Lot-size lookups (date-aware) ───────────────────────────────────────────

class TestLotSizeLookup:

    def test_finnifty_current_lot_is_65(self):
        rule = reg.get_lot_size_on("FINNIFTY", date(2025, 6, 1))
        assert rule is not None
        assert rule.lot_size == 65
        assert "2024/113" in rule.circular_ref

    def test_finnifty_pre_nov_2024_was_40(self):
        rule = reg.get_lot_size_on("FINNIFTY", date(2024, 6, 1))
        assert rule is not None
        assert rule.lot_size == 40

    def test_midcpnifty_current_lot_is_120(self):
        rule = reg.get_lot_size_on("MIDCPNIFTY", date(2025, 1, 1))
        assert rule is not None
        assert rule.lot_size == 120

    def test_alias_resolves_to_canonical(self):
        rule = reg.get_lot_size_on("^CNXFIN", date(2025, 1, 1))
        assert rule is not None
        assert rule.lot_size == 65

    def test_unknown_symbol_returns_none(self):
        assert reg.get_lot_size_on("UNKNOWN", date(2025, 1, 1)) is None


# ─── Expiry weekday lookups ──────────────────────────────────────────────────

class TestExpiryWeekday:

    def test_nifty_expiry_thursday(self):
        assert reg.get_expiry_weekday_on("NIFTY", date(2024, 6, 1)) == 3

    def test_banknifty_expiry_wednesday(self):
        assert reg.get_expiry_weekday_on("BANKNIFTY", date(2024, 6, 1)) == 2

    def test_finnifty_expiry_tuesday(self):
        assert reg.get_expiry_weekday_on("FINNIFTY", date(2024, 6, 1)) == 1

    def test_midcpnifty_expiry_monday(self):
        assert reg.get_expiry_weekday_on("MIDCPNIFTY", date(2024, 6, 1)) == 0

    def test_sensex_expiry_friday(self):
        assert reg.get_expiry_weekday_on("SENSEX", date(2024, 6, 1)) == 4


# ─── NSE holiday calendar + holiday-shifted expiries ─────────────────────────

class TestHolidaysAndExpiryShift:

    def test_republic_day_2024_is_holiday(self):
        assert reg.is_holiday(date(2024, 1, 26))
        assert not reg.is_trading_day(date(2024, 1, 26))

    def test_mahashivratri_2025_is_holiday(self):
        assert reg.is_holiday(date(2025, 2, 26))

    def test_regular_weekday_is_trading_day(self):
        # 2024-01-23 (Tuesday) is not a holiday
        assert reg.is_trading_day(date(2024, 1, 23))

    def test_saturday_not_trading_day(self):
        assert not reg.is_trading_day(date(2024, 1, 27))

    def test_sensex_jan_2024_expiry_shifts_off_republic_day(self):
        """SENSEX last-Friday in Jan 2024 = 26 Jan = Republic Day → shifts to
        25 Jan (Thursday)."""
        exps = reg.monthly_expiries("SENSEX",
                                    date(2024, 1, 1), date(2024, 1, 31),
                                    holiday_adjust=True)
        assert exps == [date(2024, 1, 25)]

    def test_banknifty_feb_2025_expiry_shifts_off_mahashivratri(self):
        """BANKNIFTY last-Wednesday in Feb 2025 = 26 Feb = Mahashivratri
        → shifts to 25 Feb (Tuesday)."""
        exps = reg.monthly_expiries("BANKNIFTY",
                                    date(2025, 2, 1), date(2025, 2, 28),
                                    holiday_adjust=True)
        assert exps == [date(2025, 2, 25)]

    def test_holiday_shift_disabled_returns_raw_date(self):
        exps = reg.monthly_expiries("SENSEX",
                                    date(2024, 1, 1), date(2024, 1, 31),
                                    holiday_adjust=False)
        assert exps == [date(2024, 1, 26)]


# ─── Strike step ─────────────────────────────────────────────────────────────

class TestStrikeStep:

    def test_step_for_nifty(self):
        # NIFTY contract spec is 50-point strikes regardless of spot
        assert reg.get_strike_step("NIFTY", 22_000) == 50.0
        assert reg.get_strike_step("NIFTY", 18_000) == 50.0

    def test_step_for_banknifty_and_sensex(self):
        assert reg.get_strike_step("BANKNIFTY", 50_000) == 100.0
        assert reg.get_strike_step("SENSEX", 80_000) == 100.0

    def test_step_for_midcap(self):
        # MIDCPNIFTY contract spec is 25-point strikes
        assert reg.get_strike_step("MIDCPNIFTY", 12_000) == 25.0

    def test_step_for_finnifty(self):
        assert reg.get_strike_step("FINNIFTY", 21_000) == 50.0

    def test_step_for_unknown_symbol_falls_back_to_legacy_ladder(self):
        # Legacy spot-bucketed ladder preserved for non-index symbols
        assert reg.get_strike_step("RELIANCE", 1_500) == 20.0
        assert reg.get_strike_step("", 600) == 10.0


# ─── Cost calculator ─────────────────────────────────────────────────────────

class TestCostCalculator:

    def test_sell_premium_charges_stt(self):
        """Selling options premium is hit with STT @ 0.05% post-Oct 2024."""
        cb = reg.compute_leg_costs(
            action="sell", premium=100.0, quantity=75,
            is_entry=True, on_date=date(2025, 6, 1),
        )
        # STT = 100 * 75 * 0.0005 = 3.75
        assert cb.stt == pytest.approx(3.75, abs=0.01)
        assert cb.stamp_duty == 0.0  # no stamp on sell
        assert cb.brokerage > 0
        assert cb.total > cb.stt

    def test_buy_charges_stamp_not_stt(self):
        """Buy side pays stamp duty but no STT."""
        cb = reg.compute_leg_costs(
            action="buy", premium=100.0, quantity=75,
            is_entry=True, on_date=date(2025, 6, 1),
        )
        assert cb.stt == 0.0
        # Stamp = 100 * 75 * 0.00003 = 0.225
        assert cb.stamp_duty == pytest.approx(0.225, abs=0.01)

    def test_pre_oct_2024_stt_is_lower(self):
        """STT was 0.0625% before Oct 2024."""
        cb = reg.compute_leg_costs(
            action="sell", premium=100.0, quantity=75,
            is_entry=True, on_date=date(2024, 6, 1),
        )
        # STT = 100 * 75 * 0.000625 = 4.6875
        assert cb.stt == pytest.approx(4.6875, abs=0.01)

    def test_gst_applied_on_brokerage_plus_charges(self):
        cb = reg.compute_leg_costs(
            action="sell", premium=100.0, quantity=75,
            is_entry=True, on_date=date(2025, 6, 1),
        )
        # GST = 18% of (brokerage + exchange + sebi)
        expected_gst = 0.18 * (cb.brokerage + cb.exchange_charge + cb.sebi_charge)
        assert cb.gst == pytest.approx(expected_gst, abs=0.01)

    def test_exit_of_long_position_charges_stt(self):
        """Selling-to-close (exit of a long buy) is a sell side → STT applies."""
        cb = reg.compute_leg_costs(
            action="buy", premium=80.0, quantity=75,
            is_entry=False, on_date=date(2025, 6, 1),
        )
        assert cb.stt > 0

    def test_exercise_only_charges_stt(self):
        """Cash-settled expiry: STT on intrinsic only — no brokerage / stamp / GST."""
        cb = reg.compute_leg_costs(
            action="buy", premium=120.0, quantity=75,
            is_entry=False, on_date=date(2025, 6, 1),
            is_exercise=True,
        )
        assert cb.brokerage == 0.0
        assert cb.stamp_duty == 0.0
        assert cb.exchange_charge == 0.0
        assert cb.sebi_charge == 0.0
        assert cb.gst == 0.0
        # STT exercise = 120 * 75 * 0.00125 = 11.25
        assert cb.stt == pytest.approx(11.25, abs=0.01)
        assert cb.total == pytest.approx(cb.stt, abs=0.001)

    def test_exercise_short_side_no_costs(self):
        """At expiry, the assigned short side pays nothing extra."""
        cb = reg.compute_leg_costs(
            action="sell", premium=50.0, quantity=75,
            is_entry=False, on_date=date(2025, 6, 1),
            is_exercise=True,
        )
        assert cb.total == 0.0


class TestWeeklyExpiryAvailability:

    def test_banknifty_weekly_dropped_after_nov_2024_cutoff(self):
        """BANKNIFTY lost weekly contracts after the SEBI Nov-2024 restriction."""
        weekly = reg.weekly_expiries("BANKNIFTY",
                                     date(2025, 1, 1), date(2025, 3, 31),
                                     enforce_availability=True)
        assert weekly == []

    def test_nifty_weekly_kept_after_cutoff(self):
        """NIFTY 50 retains weekly contracts."""
        weekly = reg.weekly_expiries("NIFTY",
                                     date(2025, 1, 1), date(2025, 1, 31),
                                     enforce_availability=True)
        assert len(weekly) >= 4
        # Each entry should be a Thursday (weekday 3) — except where shifted
        # off a holiday (none in Jan 2025).
        assert all(e.weekday() == 3 for e in weekly)


# ─── Compliance snapshot endpoint payload shape ──────────────────────────────

class TestComplianceSnapshot:

    def test_snapshot_includes_all_symbols(self):
        snap = reg.compliance_snapshot(on_date=date(2025, 6, 1))
        symbols = {s["symbol"] for s in snap["symbols"]}
        assert {"NIFTY", "BANKNIFTY", "FINNIFTY",
                "MIDCPNIFTY", "SENSEX", "BANKEX"} <= symbols

    def test_snapshot_per_symbol_has_circular_ref(self):
        snap = reg.compliance_snapshot(symbol="FINNIFTY", on_date=date(2025, 6, 1))
        assert len(snap["symbols"]) == 1
        block = snap["symbols"][0]
        assert block["lot_size"]["value"] == 65
        assert "2024/113" in block["lot_size"]["circular_ref"]

    def test_snapshot_includes_cost_schedule(self):
        snap = reg.compliance_snapshot(on_date=date(2025, 6, 1))
        cs = snap["cost_schedule"]
        assert cs["stt_sell_premium_pct"] == 0.0005
        assert cs["stt_exercise_pct"] == 0.00125
        assert cs["gst_pct"] == 0.18

    def test_snapshot_lists_holidays(self):
        snap = reg.compliance_snapshot(on_date=date(2025, 6, 1))
        assert "2025-02-26" in snap["holidays_this_year"]


# ─── Strategy cost + margin estimators (drives /options/compliance) ──────────

class TestStrategyEstimators:

    def test_iron_condor_costs_and_margin(self):
        """4-leg iron condor on NIFTY @ 22000 should produce 4 cost rows and
        a non-zero margin estimate."""
        from app.routes.options import _build_synthetic_legs
        legs = _build_synthetic_legs("iron_condor", spot=22_000, symbol="NIFTY", lots=2)
        assert len(legs) == 4
        # Strikes are 50-spaced (NIFTY contract spec)
        strikes = sorted({l["strike"] for l in legs})
        assert all(s % 50 == 0 for s in strikes)

        costs = reg.estimate_strategy_costs(legs, lot_size=75, on_date=date(2025, 6, 1))
        assert len(costs["per_leg"]) == 4
        for row in costs["per_leg"]:
            assert row["entry"]["total"] > 0  # brokerage at minimum
            assert row["leg_total"] > 0
        assert costs["total"] > 0
        assert "Finance" in costs["circular_ref"]

        margin = reg.estimate_margin_inr(legs, spot=22_000, lot_size=75)
        assert margin["value"] > 0
        assert "SPAN" in margin["note"]

    def test_short_straddle_margin_uses_naked_band(self):
        from app.routes.options import _build_synthetic_legs
        legs = _build_synthetic_legs("short_straddle", spot=22_000, symbol="NIFTY", lots=1)
        margin = reg.estimate_margin_inr(legs, spot=22_000, lot_size=75)
        # 2 naked shorts: 12% × 22000 × 75 × 2 ≈ 3,96,000
        assert margin["value"] > 300_000

    def test_long_call_no_legs_when_zero_spot(self):
        from app.routes.options import _build_synthetic_legs
        legs = _build_synthetic_legs("long_call", spot=0.0, symbol="NIFTY", lots=1)
        assert legs == []
        costs = reg.estimate_strategy_costs(legs, lot_size=75)
        assert costs["per_leg"] == []
        assert costs["total"] == 0


class TestSymbolAwareDefaults:

    def test_options_service_strike_step_uses_symbol(self):
        from app.services.options_service import _strike_step, atm_strike
        # Symbol-aware: BANKNIFTY @ 50_000 → 100 step (matches legacy too)
        assert _strike_step(50_000, "BANKNIFTY") == 100.0
        # Symbol-aware: MIDCPNIFTY @ 12_000 → 25 step (legacy would return 100)
        assert _strike_step(12_000, "MIDCPNIFTY") == 25.0
        assert atm_strike(12_017, "MIDCPNIFTY") == 12_025
        # No-symbol path preserves legacy spot-bucketed ladder
        assert _strike_step(12_000) == 100.0

    def test_backtest_strike_step_uses_symbol(self):
        from app.services.options_backtest_service import _strike_step as bt_step
        assert bt_step(12_000, "MIDCPNIFTY") == 25.0
        assert bt_step(22_000, "NIFTY") == 50.0
        # No symbol → legacy ladder preserved
        assert bt_step(12_000) == 100.0

    def test_risk_free_rate_constant_comes_from_cache(self):
        from app.services import options_service, risk_free_service
        # The module-level constant should match the synchronous cache helper
        assert options_service.RISK_FREE_RATE == risk_free_service.get_cached_rate_sync()
        # Refreshing the helper updates the constant
        new = options_service.get_default_risk_free_rate()
        assert options_service.RISK_FREE_RATE == new
