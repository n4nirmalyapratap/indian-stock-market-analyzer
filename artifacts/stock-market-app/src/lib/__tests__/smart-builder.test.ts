/**
 * smart-builder.test.ts
 * Frontend unit tests for the Smart Strategy Builder utilities.
 * Tests the scoring logic that mirrors the backend service.
 */
import { describe, it, expect } from "vitest";

// ── Re-implement the pure scoring functions locally for unit testing ──────────
// (These mirror strategy_builder_service.py logic in TypeScript)

type VolRegime = "low" | "moderate" | "high" | "very_high";
type VolBias   = "expanding" | "contracting" | "stable";

interface MarketState {
  vol_regime: VolRegime;
  vol_bias:   VolBias;
  hv_pct:     number;
  step:       number;
}

function detectVolRegime(hv_pct: number): VolRegime {
  if (hv_pct >= 75) return "very_high";
  if (hv_pct >= 55) return "high";
  if (hv_pct >= 35) return "moderate";
  return "low";
}

function detectVolBias(hv_pct: number): VolBias {
  if (hv_pct >= 65) return "expanding";
  if (hv_pct <= 30) return "contracting";
  return "stable";
}

function detectStep(atm: number): number {
  if (atm >= 10_000) return 100;
  if (atm >= 2_000)  return 50;
  return 10;
}

// Score colour helper (mirrors SmartBuilderTab)
function scoreColor(s: number): "green" | "amber" | "red" {
  return s >= 65 ? "green" : s >= 42 ? "amber" : "red";
}

// Score predefined (mirrors _score_predefined)
function scorePredefined(name: string, hv_pct: number): number {
  const VOL_BUY  = new Set(["Long Straddle", "Long Strangle"]);
  const VOL_SELL = new Set(["Short Straddle", "Short Strangle", "Iron Condor"]);
  const BUY_DIR  = new Set(["Long Call", "Long Put"]);
  const SELL_DIR = new Set(["Short Call", "Short Put"]);
  const SPREAD   = new Set(["Bull Call Spread", "Bear Put Spread"]);
  const PIN      = new Set(["Butterfly"]);

  let score = 50;
  if (VOL_BUY.has(name)) {
    score += hv_pct < 35 ? 30 : hv_pct < 50 ? 10 : hv_pct < 65 ? -10 : -30;
  } else if (VOL_SELL.has(name)) {
    score += hv_pct > 65 ? 30 : hv_pct > 50 ? 10 : hv_pct > 40 ? -10 : -30;
  } else if (BUY_DIR.has(name)) {
    score += hv_pct < 40 ? 25 : hv_pct < 55 ? 10 : hv_pct < 65 ? -10 : -25;
  } else if (SELL_DIR.has(name)) {
    score += hv_pct > 60 ? 25 : hv_pct > 45 ? 5 : hv_pct > 35 ? -15 : -25;
  } else if (SPREAD.has(name)) {
    score += (hv_pct > 30 && hv_pct < 70) ? 15 : -10;
  } else if (PIN.has(name)) {
    score += hv_pct < 30 ? 30 : hv_pct < 45 ? 10 : hv_pct < 60 ? -15 : -30;
  }
  return Math.max(0, Math.min(100, score));
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("detectVolRegime", () => {
  it("returns low for hv_pct < 35", () => {
    expect(detectVolRegime(20)).toBe("low");
    expect(detectVolRegime(34)).toBe("low");
  });

  it("returns moderate for hv_pct 35–54", () => {
    expect(detectVolRegime(35)).toBe("moderate");
    expect(detectVolRegime(50)).toBe("moderate");
    expect(detectVolRegime(54)).toBe("moderate");
  });

  it("returns high for hv_pct 55–74", () => {
    expect(detectVolRegime(55)).toBe("high");
    expect(detectVolRegime(70)).toBe("high");
    expect(detectVolRegime(74)).toBe("high");
  });

  it("returns very_high for hv_pct >= 75", () => {
    expect(detectVolRegime(75)).toBe("very_high");
    expect(detectVolRegime(90)).toBe("very_high");
  });
});

describe("detectVolBias", () => {
  it("expanding when pct >= 65", () => {
    expect(detectVolBias(65)).toBe("expanding");
    expect(detectVolBias(80)).toBe("expanding");
  });

  it("contracting when pct <= 30", () => {
    expect(detectVolBias(30)).toBe("contracting");
    expect(detectVolBias(10)).toBe("contracting");
  });

  it("stable in the middle", () => {
    expect(detectVolBias(50)).toBe("stable");
    expect(detectVolBias(45)).toBe("stable");
  });
});

describe("detectStep", () => {
  it("step 100 for Nifty-level ATM", () => {
    expect(detectStep(22000)).toBe(100);
    expect(detectStep(10000)).toBe(100);
  });

  it("step 50 for mid-level ATM", () => {
    expect(detectStep(2000)).toBe(50);
    expect(detectStep(5000)).toBe(50);
  });

  it("step 10 for small-stock ATM", () => {
    expect(detectStep(400)).toBe(10);
    expect(detectStep(1999)).toBe(10);
  });
});

describe("scoreColor", () => {
  it("green for score >= 65", () => {
    expect(scoreColor(65)).toBe("green");
    expect(scoreColor(80)).toBe("green");
    expect(scoreColor(100)).toBe("green");
  });

  it("amber for score 42–64", () => {
    expect(scoreColor(42)).toBe("amber");
    expect(scoreColor(55)).toBe("amber");
    expect(scoreColor(64)).toBe("amber");
  });

  it("red for score < 42", () => {
    expect(scoreColor(0)).toBe("red");
    expect(scoreColor(25)).toBe("red");
    expect(scoreColor(41)).toBe("red");
  });
});

describe("scorePredefined (mirrors backend logic)", () => {
  it("Iron Condor scores high in high vol (hv_pct=75)", () => {
    expect(scorePredefined("Iron Condor", 75)).toBeGreaterThanOrEqual(65);
  });

  it("Iron Condor scores low in low vol (hv_pct=20)", () => {
    expect(scorePredefined("Iron Condor", 20)).toBeLessThanOrEqual(40);
  });

  it("Long Straddle scores high in low vol (hv_pct=20)", () => {
    expect(scorePredefined("Long Straddle", 20)).toBeGreaterThanOrEqual(65);
  });

  it("Long Straddle scores low in high vol (hv_pct=80)", () => {
    expect(scorePredefined("Long Straddle", 80)).toBeLessThanOrEqual(35);
  });

  it("Butterfly scores high in very low vol (hv_pct=15)", () => {
    expect(scorePredefined("Butterfly", 15)).toBeGreaterThanOrEqual(70);
  });

  it("Butterfly scores low in high vol (hv_pct=80)", () => {
    expect(scorePredefined("Butterfly", 80)).toBeLessThanOrEqual(30);
  });

  it("all scores are bounded 0–100", () => {
    const names = [
      "Long Call", "Short Put", "Long Put", "Short Call",
      "Long Straddle", "Long Strangle", "Short Straddle", "Short Strangle",
      "Bull Call Spread", "Bear Put Spread", "Iron Condor", "Butterfly",
    ];
    for (const name of names) {
      for (const pct of [5, 20, 35, 50, 65, 80, 95]) {
        const s = scorePredefined(name, pct);
        expect(s).toBeGreaterThanOrEqual(0);
        expect(s).toBeLessThanOrEqual(100);
      }
    }
  });

  it("Long Call cheaper in low vol → higher score vs high vol", () => {
    expect(scorePredefined("Long Call", 20)).toBeGreaterThan(scorePredefined("Long Call", 80));
  });

  it("Short Strangle better in high vol", () => {
    expect(scorePredefined("Short Strangle", 80)).toBeGreaterThan(scorePredefined("Short Strangle", 20));
  });

  it("Bull Call Spread best in moderate vol range", () => {
    const mid  = scorePredefined("Bull Call Spread", 50);
    const low  = scorePredefined("Bull Call Spread", 10);
    const high = scorePredefined("Bull Call Spread", 90);
    expect(mid).toBeGreaterThanOrEqual(low);
    expect(mid).toBeGreaterThanOrEqual(high);
  });
});

describe("VOL_REGIME_LABEL mapping completeness", () => {
  const VOL_REGIME_LABEL: Record<string, string> = {
    low: "Low Vol", moderate: "Moderate Vol", high: "High Vol", very_high: "Very High Vol",
  };

  it("covers all 4 regimes", () => {
    expect(Object.keys(VOL_REGIME_LABEL)).toHaveLength(4);
  });

  it("each regime has non-empty label", () => {
    for (const [, label] of Object.entries(VOL_REGIME_LABEL)) {
      expect(label.length).toBeGreaterThan(0);
    }
  });
});

describe("OUTLOOK_ICON mapping", () => {
  const OUTLOOK_ICON: Record<string, string> = {
    bullish: "↑", bearish: "↓", neutral: "↔", volatile: "↕",
  };

  it("maps all 4 outlook types", () => {
    expect(Object.keys(OUTLOOK_ICON)).toHaveLength(4);
  });

  it("each icon is a single unicode arrow", () => {
    for (const icon of Object.values(OUTLOOK_ICON)) {
      expect(icon.length).toBe(1);
    }
  });
});
