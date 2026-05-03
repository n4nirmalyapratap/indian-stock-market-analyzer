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

    def test_step_for_nifty_range(self):
        assert reg.get_strike_step("NIFTY", 22_000) == 100.0

    def test_step_for_midcap_range(self):
        assert reg.get_strike_step("MIDCPNIFTY", 12_000) == 100.0

    def test_step_for_individual_stock_range(self):
        assert reg.get_strike_step("RELIANCE", 1_500) == 20.0


# ─── Cost calculator ─────────────────────────────────────────────────────────

class TestCostCalculator:

    def test_sell_premium_charges_stt(self):
        """Selling options premium is hit with STT @ 0.10% post-Oct 2024."""
        cb = reg.compute_leg_costs(
            action="sell", premium=100.0, quantity=75,
            is_entry=True, on_date=date(2025, 6, 1),
        )
        # STT = 100 * 75 * 0.001 = 7.5
        assert cb.stt == pytest.approx(7.5, abs=0.01)
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
        assert cs["stt_sell_premium_pct"] == 0.0010
        assert cs["gst_pct"] == 0.18

    def test_snapshot_lists_holidays(self):
        snap = reg.compliance_snapshot(on_date=date(2025, 6, 1))
        assert "2025-02-26" in snap["holidays_this_year"]
