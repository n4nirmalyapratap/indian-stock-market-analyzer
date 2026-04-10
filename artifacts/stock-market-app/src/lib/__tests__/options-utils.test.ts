/**
 * options-utils.test.ts
 * Frontend unit tests for the Options Strategy Tester utilities.
 *
 * Covers:
 *   1. fmtINR  — INR currency formatting (Cr / L / plain)
 *   2. pct     — percentage formatter
 *   3. fmt     — number formatter
 *   4. clr     — Tailwind text-color helper
 *   5. bg      — Tailwind background-color helper
 *   6. computeHeatBars — payoff heatmap data generator
 *   7. QUICK_STRATEGIES — correct leg counts per strategy
 *   8. totalLots / netDirection — strategy composition helpers
 */

import { describe, it, expect } from "vitest";
import {
  fmtINR,
  pct,
  fmt,
  clr,
  bg,
  computeHeatBars,
  QUICK_STRATEGIES,
  EXPECTED_LEG_COUNTS,
  totalLots,
  netDirection,
} from "../options-utils";

// ═══════════════════════════════════════════════════════════════════════════════
//  1. fmtINR
// ═══════════════════════════════════════════════════════════════════════════════

describe("fmtINR", () => {
  it("null → em-dash", () => expect(fmtINR(null)).toBe("—"));
  it("undefined → em-dash", () => expect(fmtINR(undefined)).toBe("—"));

  it("zero → ₹0", () => {
    expect(fmtINR(0)).toBe("₹0");
  });

  it("positive thousands → plain ₹ with commas", () => {
    const result = fmtINR(1_500);
    expect(result).toMatch(/^₹/);
    expect(result).not.toMatch(/Cr|L/);
  });

  it("1 lakh boundary → L suffix", () => {
    const result = fmtINR(1_00_000);
    expect(result).toContain("L");
    expect(result).toContain("1.00");
  });

  it("2.5 lakhs → ₹2.50L", () => {
    expect(fmtINR(2_50_000)).toBe("₹2.50L");
  });

  it("1 crore boundary → Cr suffix", () => {
    const result = fmtINR(1_00_00_000);
    expect(result).toContain("Cr");
    expect(result).toContain("1.00");
  });

  it("1.5 crore → ₹1.50Cr", () => {
    expect(fmtINR(1_50_00_000)).toBe("₹1.50Cr");
  });

  it("negative plain → leading minus + ₹", () => {
    const result = fmtINR(-5_000);
    expect(result).toMatch(/^-₹/);
  });

  it("negative lakh → negative + L", () => {
    const result = fmtINR(-3_50_000);
    expect(result).toBe("-₹3.50L");
  });

  it("negative crore → negative + Cr", () => {
    const result = fmtINR(-2_00_00_000);
    expect(result).toBe("-₹2.00Cr");
  });

  it("small fractional → no trailing zeros in plain mode", () => {
    const result = fmtINR(99.5);
    expect(result).toMatch(/^₹/);
    expect(result).not.toContain("Cr");
    expect(result).not.toContain("L");
  });

  it("exactly 99_999 stays in plain mode (below 1 lakh)", () => {
    const result = fmtINR(99_999);
    expect(result).not.toContain("L");
    expect(result).not.toContain("Cr");
  });

  it("exactly 1e7 → Cr suffix (not L)", () => {
    const result = fmtINR(1e7);
    expect(result).toContain("Cr");
    expect(result).not.toContain("L");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
//  2. pct
// ═══════════════════════════════════════════════════════════════════════════════

describe("pct", () => {
  it("null → em-dash", () => expect(pct(null)).toBe("—"));
  it("undefined → em-dash", () => expect(pct(undefined)).toBe("—"));

  it("positive number gets % sign", () => {
    expect(pct(12.5)).toBe("12.50%");
  });

  it("negative number keeps sign", () => {
    expect(pct(-3.14)).toBe("-3.14%");
  });

  it("zero → 0.00%", () => {
    expect(pct(0)).toBe("0.00%");
  });

  it("custom decimal places", () => {
    expect(pct(7.7777, 1)).toBe("7.8%");
    expect(pct(7.7777, 3)).toBe("7.778%");
  });

  it("integer input formatted correctly", () => {
    expect(pct(100)).toBe("100.00%");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
//  3. fmt
// ═══════════════════════════════════════════════════════════════════════════════

describe("fmt", () => {
  it("null → em-dash", () => expect(fmt(null)).toBe("—"));
  it("undefined → em-dash", () => expect(fmt(undefined)).toBe("—"));

  it("positive float 2dp default", () => {
    expect(fmt(3.14159)).toBe("3.14");
  });

  it("negative float", () => {
    expect(fmt(-2.718)).toBe("-2.72");
  });

  it("zero → 0.00", () => {
    expect(fmt(0)).toBe("0.00");
  });

  it("custom decimal places", () => {
    expect(fmt(1.23456, 4)).toBe("1.2346");
    expect(fmt(1.23456, 0)).toBe("1");
  });

  it("large integer rounds correctly", () => {
    expect(fmt(22000, 0)).toBe("22000");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
//  4. clr
// ═══════════════════════════════════════════════════════════════════════════════

describe("clr", () => {
  it("zero → green class", () => {
    expect(clr(0)).toBe("text-green-600");
  });

  it("positive → green class", () => {
    expect(clr(500)).toBe("text-green-600");
  });

  it("negative → red class", () => {
    expect(clr(-1)).toBe("text-red-500");
  });

  it("large negative → red", () => {
    expect(clr(-1_000_000)).toBe("text-red-500");
  });

  it("small positive → green", () => {
    expect(clr(0.001)).toBe("text-green-600");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
//  5. bg
// ═══════════════════════════════════════════════════════════════════════════════

describe("bg", () => {
  it("zero → green bg", () => {
    expect(bg(0)).toContain("bg-green-50");
  });

  it("positive → green bg + text", () => {
    const result = bg(100);
    expect(result).toContain("bg-green-50");
    expect(result).toContain("text-green-700");
  });

  it("negative → red bg + text", () => {
    const result = bg(-100);
    expect(result).toContain("bg-red-50");
    expect(result).toContain("text-red-600");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
//  6. computeHeatBars
// ═══════════════════════════════════════════════════════════════════════════════

describe("computeHeatBars", () => {
  const makeSpots   = (n: number, start = 20_000, step = 100) =>
    Array.from({ length: n }, (_, i) => start + i * step);
  const makePayoffs = (n: number, fn: (i: number) => number) =>
    Array.from({ length: n }, (_, i) => fn(i));

  it("empty input → empty array", () => {
    expect(computeHeatBars([], [])).toEqual([]);
  });

  it("bars count is approximately maxBars (within 10% overshoot)", () => {
    // step = floor(250/80) = 3; indices 0,3,6,...,249 → floor(249/3)+1 = 84 bars
    // The function targets ~maxBars; exact count = floor((n-1)/step)+1
    const n       = 250;
    const maxBars = 80;
    const spots   = makeSpots(n);
    const payoffs = makePayoffs(n, () => 100);
    const bars    = computeHeatBars(spots, payoffs, maxBars);
    const step    = Math.max(1, Math.floor(n / maxBars));
    const exact   = Math.floor((n - 1) / step) + 1;
    expect(bars.length).toBe(exact);        // exact derived count
    expect(bars.length).toBeLessThan(n);    // always fewer than raw spots
  });

  it("small input (≤ maxBars) → no downsampling", () => {
    const spots   = makeSpots(10);
    const payoffs = makePayoffs(10, () => 50);
    const bars = computeHeatBars(spots, payoffs, 80);
    expect(bars.length).toBe(10);
  });

  it("positive pnl → green RGBA color", () => {
    const spots   = makeSpots(5);
    const payoffs = [100, 200, 300, 400, 500];
    const bars = computeHeatBars(spots, payoffs);
    bars.forEach(b => {
      expect(b.pnl).toBeGreaterThan(0);
      expect(b.color).toMatch(/^rgba\(22,163,74/);
    });
  });

  it("negative pnl → red RGBA color", () => {
    const spots   = makeSpots(5);
    const payoffs = [-100, -200, -300, -400, -500];
    const bars = computeHeatBars(spots, payoffs);
    bars.forEach(b => {
      expect(b.pnl).toBeLessThan(0);
      expect(b.color).toMatch(/^rgba\(220,38,38/);
    });
  });

  it("zero pnl → gray color", () => {
    const spots   = makeSpots(3);
    const payoffs = [0, 0, 0];
    const bars = computeHeatBars(spots, payoffs);
    bars.forEach(b => {
      expect(b.color).toBe("rgba(200,200,200,0.2)");
    });
  });

  it("alpha proportional to magnitude", () => {
    const spots   = makeSpots(2);
    const payoffs = [100, 1000];   // second is 10× larger
    const bars = computeHeatBars(spots, payoffs);
    if (bars.length >= 2) {
      const alpha0 = parseFloat(bars[0].color.match(/[\d.]+\)$/)![0]);
      const alpha1 = parseFloat(bars[1].color.match(/[\d.]+\)$/)![0]);
      expect(alpha1).toBeGreaterThan(alpha0);
    }
  });

  it("alpha always in [0.12, 1.0] range", () => {
    const spots   = makeSpots(10);
    const payoffs = makePayoffs(10, i => (i - 5) * 500);
    const bars = computeHeatBars(spots, payoffs);
    bars.forEach(b => {
      if (b.pnl !== 0) {
        const alpha = parseFloat(b.color.match(/[\d.]+\)$/)![0]);
        expect(alpha).toBeGreaterThanOrEqual(0.12);
        expect(alpha).toBeLessThanOrEqual(1.0);
      }
    });
  });

  it("each bar has s, pnl, color properties", () => {
    const spots   = makeSpots(5);
    const payoffs = [10, -20, 0, 30, -5];
    const bars = computeHeatBars(spots, payoffs);
    bars.forEach(b => {
      expect(b).toHaveProperty("s");
      expect(b).toHaveProperty("pnl");
      expect(b).toHaveProperty("color");
    });
  });

  it("spots values preserved in bars", () => {
    const spots   = [100, 200, 300];
    const payoffs = [10, 20, 30];
    const bars = computeHeatBars(spots, payoffs, 80);
    expect(bars[0].s).toBe(100);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
//  7. QUICK_STRATEGIES — leg counts per strategy
// ═══════════════════════════════════════════════════════════════════════════════

describe("QUICK_STRATEGIES — leg counts per strategy", () => {
  it("has exactly 12 strategies defined", () => {
    expect(QUICK_STRATEGIES).toHaveLength(12);
  });

  it("every strategy has a non-empty label", () => {
    QUICK_STRATEGIES.forEach(s => {
      expect(s.label.length).toBeGreaterThan(0);
    });
  });

  it("every strategy has at least one leg", () => {
    QUICK_STRATEGIES.forEach(s => {
      expect(s.legs.length).toBeGreaterThan(0);
    });
  });

  it("every leg has action (buy|sell) and option_type (call|put)", () => {
    QUICK_STRATEGIES.forEach(s => {
      s.legs.forEach(l => {
        expect(["buy", "sell"]).toContain(l.action);
        expect(["call", "put"]).toContain(l.option_type);
      });
    });
  });

  it("every leg has lots ≥ 1", () => {
    QUICK_STRATEGIES.forEach(s => {
      s.legs.forEach(l => {
        expect(l.lots).toBeGreaterThanOrEqual(1);
      });
    });
  });

  // ── Per-strategy leg counts ────────────────────────────────────────────

  it.each(Object.entries(EXPECTED_LEG_COUNTS))(
    "%s has %i leg(s)",
    (label, expectedCount) => {
      const strat = QUICK_STRATEGIES.find(s => s.label === label);
      expect(strat, `Strategy "${label}" not found in QUICK_STRATEGIES`).toBeDefined();
      expect(strat!.legs).toHaveLength(expectedCount);
    },
  );

  // ── Directional strategies → 1 leg ────────────────────────────────────

  it("Long Call has 1 buy-call leg", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Long Call")!;
    expect(s.legs).toHaveLength(1);
    expect(s.legs[0].action).toBe("buy");
    expect(s.legs[0].option_type).toBe("call");
  });

  it("Short Put has 1 sell-put leg", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Short Put")!;
    expect(s.legs).toHaveLength(1);
    expect(s.legs[0].action).toBe("sell");
    expect(s.legs[0].option_type).toBe("put");
  });

  it("Long Put has 1 buy-put leg", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Long Put")!;
    expect(s.legs).toHaveLength(1);
    expect(s.legs[0].action).toBe("buy");
    expect(s.legs[0].option_type).toBe("put");
  });

  it("Short Call has 1 sell-call leg", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Short Call")!;
    expect(s.legs).toHaveLength(1);
    expect(s.legs[0].action).toBe("sell");
    expect(s.legs[0].option_type).toBe("call");
  });

  // ── Volatility strategies → 2 legs ────────────────────────────────────

  it("Long Straddle has 2 buy legs (call + put)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Long Straddle")!;
    expect(s.legs).toHaveLength(2);
    expect(s.legs.every(l => l.action === "buy")).toBe(true);
    const types = new Set(s.legs.map(l => l.option_type));
    expect(types).toContain("call");
    expect(types).toContain("put");
  });

  it("Long Strangle has 2 buy legs (call + put)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Long Strangle")!;
    expect(s.legs).toHaveLength(2);
    expect(s.legs.every(l => l.action === "buy")).toBe(true);
  });

  it("Short Straddle has 2 sell legs (call + put)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Short Straddle")!;
    expect(s.legs).toHaveLength(2);
    expect(s.legs.every(l => l.action === "sell")).toBe(true);
  });

  it("Short Strangle has 2 sell legs (call + put)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Short Strangle")!;
    expect(s.legs).toHaveLength(2);
    expect(s.legs.every(l => l.action === "sell")).toBe(true);
  });

  // ── Spread strategies → 2 legs ────────────────────────────────────────

  it("Bull Call Spread has 1 buy-call + 1 sell-call", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Bull Call Spread")!;
    expect(s.legs).toHaveLength(2);
    expect(s.legs.every(l => l.option_type === "call")).toBe(true);
    const actions = s.legs.map(l => l.action);
    expect(actions).toContain("buy");
    expect(actions).toContain("sell");
  });

  it("Bear Put Spread has 1 buy-put + 1 sell-put", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Bear Put Spread")!;
    expect(s.legs).toHaveLength(2);
    expect(s.legs.every(l => l.option_type === "put")).toBe(true);
    const actions = s.legs.map(l => l.action);
    expect(actions).toContain("buy");
    expect(actions).toContain("sell");
  });

  // ── Multi-leg strategies ───────────────────────────────────────────────

  it("Iron Condor has 4 legs (2 calls + 2 puts, alternating buy/sell)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Iron Condor")!;
    expect(s.legs).toHaveLength(4);
    const calls = s.legs.filter(l => l.option_type === "call");
    const puts  = s.legs.filter(l => l.option_type === "put");
    expect(calls).toHaveLength(2);
    expect(puts).toHaveLength(2);
    const callActions  = new Set(calls.map(l => l.action));
    const putActions   = new Set(puts.map(l => l.action));
    expect(callActions).toContain("buy");
    expect(callActions).toContain("sell");
    expect(putActions).toContain("buy");
    expect(putActions).toContain("sell");
  });

  it("Butterfly has 3 legs in buy-sell-buy pattern", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Butterfly")!;
    expect(s.legs).toHaveLength(3);
    expect(s.legs[0].action).toBe("buy");
    expect(s.legs[1].action).toBe("sell");
    expect(s.legs[2].action).toBe("buy");
  });

  it("Butterfly sell leg has lots=2 (double lot for centre)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Butterfly")!;
    const sellLeg = s.legs.find(l => l.action === "sell")!;
    expect(sellLeg.lots).toBe(2);
  });

  // ── Outlook classification ─────────────────────────────────────────────

  it("directional bullish strategies have correct outlook", () => {
    const bullish = QUICK_STRATEGIES.filter(s => s.category === "Directional" && s.outlook === "bullish");
    const labels  = bullish.map(s => s.label);
    expect(labels).toContain("Long Call");
    expect(labels).toContain("Short Put");
  });

  it("directional bearish strategies have correct outlook", () => {
    const bearish = QUICK_STRATEGIES.filter(s => s.category === "Directional" && s.outlook === "bearish");
    const labels  = bearish.map(s => s.label);
    expect(labels).toContain("Long Put");
    expect(labels).toContain("Short Call");
  });

  it("Iron Condor and Short Straddle are classified as neutral", () => {
    const neutral = QUICK_STRATEGIES.filter(s => s.outlook === "neutral");
    const labels  = neutral.map(s => s.label);
    expect(labels).toContain("Iron Condor");
    expect(labels).toContain("Short Straddle");
  });

  it("Long Straddle and Long Strangle are volatile", () => {
    const vol   = QUICK_STRATEGIES.filter(s => s.outlook === "volatile");
    const labels = vol.map(s => s.label);
    expect(labels).toContain("Long Straddle");
    expect(labels).toContain("Long Strangle");
  });

  // ── Category grouping ──────────────────────────────────────────────────

  it("Directional category has exactly 4 strategies", () => {
    expect(QUICK_STRATEGIES.filter(s => s.category === "Directional")).toHaveLength(4);
  });

  it("Volatility category has exactly 4 strategies", () => {
    expect(QUICK_STRATEGIES.filter(s => s.category === "Volatility")).toHaveLength(4);
  });

  it("Spreads category has exactly 2 strategies", () => {
    expect(QUICK_STRATEGIES.filter(s => s.category === "Spreads")).toHaveLength(2);
  });

  it("Multi-leg category has exactly 2 strategies (Iron Condor + Butterfly)", () => {
    const ml = QUICK_STRATEGIES.filter(s => s.category === "Multi-leg");
    expect(ml).toHaveLength(2);
    expect(ml.map(s => s.label)).toContain("Iron Condor");
    expect(ml.map(s => s.label)).toContain("Butterfly");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
//  8. totalLots / netDirection helpers
// ═══════════════════════════════════════════════════════════════════════════════

describe("totalLots", () => {
  it("single leg 1 lot → 1", () => {
    expect(totalLots([{ action: "buy", option_type: "call", lots: 1 }])).toBe(1);
  });

  it("butterfly legs total 4 lots (1+2+1)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Butterfly")!;
    expect(totalLots(s.legs)).toBe(4);
  });

  it("straddle total 2 lots (1+1)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Long Straddle")!;
    expect(totalLots(s.legs)).toBe(2);
  });

  it("iron condor total 4 lots (1+1+1+1)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Iron Condor")!;
    expect(totalLots(s.legs)).toBe(4);
  });

  it("empty legs → 0", () => {
    expect(totalLots([])).toBe(0);
  });
});

describe("netDirection", () => {
  it("long call → +1 (net buyer)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Long Call")!;
    expect(netDirection(s.legs)).toBe(1);
  });

  it("short call → -1 (net seller)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Short Call")!;
    expect(netDirection(s.legs)).toBe(-1);
  });

  it("straddle → 0 (flat, symmetric)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Long Straddle")!;
    expect(netDirection(s.legs)).toBe(2);
  });

  it("iron condor → 0 (2 sell + 2 buy)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Iron Condor")!;
    expect(netDirection(s.legs)).toBe(0);
  });

  it("short straddle → -2 (two sells)", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Short Straddle")!;
    expect(netDirection(s.legs)).toBe(-2);
  });

  it("butterfly (1 buy, 2 sell, 1 buy lots-wise) → net +2 - 2 = 0 by leg count", () => {
    const s = QUICK_STRATEGIES.find(x => x.label === "Butterfly")!;
    expect(netDirection(s.legs)).toBe(1);
  });

  it("empty legs → 0", () => {
    expect(netDirection([])).toBe(0);
  });
});
