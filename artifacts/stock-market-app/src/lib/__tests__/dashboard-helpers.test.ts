import { describe, it, expect } from "vitest";
import {
  formatAdRatio,
  shortSectorName,
  formatPctChange,
} from "../../pages/Dashboard";
import {
  pickMeta,
  isMarketOpenIST,
  marketDataQueryOptions,
} from "../marketData";

// ─── formatAdRatio ──────────────────────────────────────────────────────────
describe("formatAdRatio", () => {
  it("computes a normal ratio with 2 decimal places", () => {
    expect(formatAdRatio(10, 5)).toBe("2.00");
    expect(formatAdRatio(5, 10)).toBe("0.50");
    expect(formatAdRatio(1, 3)).toBe("0.33");
  });

  it("returns ∞ when declining is 0 but advancing is positive", () => {
    // The previous implementation wrongly displayed the advancing count
    // as if it were a ratio (e.g. 15.00 for 15:0). That's misleading.
    expect(formatAdRatio(15, 0)).toBe("∞");
    expect(formatAdRatio(1, 0)).toBe("∞");
  });

  it("returns em-dash when there is no breadth at all", () => {
    expect(formatAdRatio(0, 0)).toBe("—");
  });

  it("zero advancing with positive declining is 0.00, not em-dash", () => {
    // A genuinely bearish day should read 0.00, not "—".
    expect(formatAdRatio(0, 50)).toBe("0.00");
  });

  it("never returns NaN or Infinity", () => {
    const cases: [number, number][] = [
      [10, 5], [0, 0], [5, 0], [0, 5], [100, 1], [1, 100],
    ];
    for (const [a, d] of cases) {
      const r = formatAdRatio(a, d);
      expect(r).not.toContain("NaN");
      expect(r).not.toContain("Infinity");
    }
  });
});

// ─── shortSectorName ────────────────────────────────────────────────────────
describe("shortSectorName", () => {
  it("strips the 'Nifty ' prefix from named sectors", () => {
    expect(shortSectorName("Nifty Bank")).toBe("Bank");
    expect(shortSectorName("Nifty IT")).toBe("IT");
    expect(shortSectorName("Nifty Auto")).toBe("Auto");
    expect(shortSectorName("Nifty Pharma")).toBe("Pharma");
  });

  it("preserves 'Nifty 50' / 'Nifty 100' so the label isn't a bare number", () => {
    // Regression: previously rendered as "50" — ambiguous next to "Bank".
    expect(shortSectorName("Nifty 50")).toBe("Nifty 50");
    expect(shortSectorName("Nifty 100")).toBe("Nifty 100");
    expect(shortSectorName("Nifty 500")).toBe("Nifty 500");
    expect(shortSectorName("Nifty Next 50")).toBe("Nifty Next 50");
  });

  it("is case-insensitive on the prefix", () => {
    expect(shortSectorName("nifty Bank")).toBe("Bank");
    expect(shortSectorName("NIFTY BANK")).toBe("BANK");
  });

  it("handles non-Nifty names unchanged", () => {
    expect(shortSectorName("BSE Sensex")).toBe("BSE Sensex");
    expect(shortSectorName("")).toBe("");
  });
});

// ─── formatPctChange ────────────────────────────────────────────────────────
describe("formatPctChange", () => {
  it("formats positive with leading +", () => {
    expect(formatPctChange(1.234)).toBe("+1.23%");
    expect(formatPctChange(0.005)).toBe("+0.01%");      // rounds, still positive
  });

  it("formats negative with the - sign", () => {
    expect(formatPctChange(-1.234)).toBe("-1.23%");
    expect(formatPctChange(-0.01)).toBe("-0.01%");
  });

  it("renders 0 as +0.00%, not '0' or 'NaN'", () => {
    // Regression: previous code did `s.pChange?.toFixed(2) || "0"`, which
    // when pChange === 0 returned "0" (no decimals). Now it returns +0.00%.
    expect(formatPctChange(0)).toBe("+0.00%");
  });

  it("renders null/undefined/NaN as '—' (not '+0.00%')", () => {
    // Regression: previously this collapsed null to 0 with `?? 0`, which
    // hid data-fetch failures behind a fake "+0.00%". Honest UX: show "—"
    // so the user can tell "no data" from "actually flat".
    expect(formatPctChange(null)).toBe("—");
    expect(formatPctChange(undefined)).toBe("—");
    expect(formatPctChange(NaN)).toBe("—");
  });

  it("always has 2 decimal places", () => {
    for (const v of [1, -1, 0, 0.5, -0.5, 100, -100, 0.001]) {
      expect(formatPctChange(v)).toMatch(/^[+-]\d+\.\d{2}%$/);
    }
  });
});

// ─── pickMeta ───────────────────────────────────────────────────────────────
describe("pickMeta", () => {
  it("returns null for nullish or non-object input", () => {
    expect(pickMeta(null)).toBeNull();
    expect(pickMeta(undefined)).toBeNull();
    expect(pickMeta(42)).toBeNull();
    expect(pickMeta("x")).toBeNull();
  });

  it("returns null when meta is missing", () => {
    expect(pickMeta({})).toBeNull();
    expect(pickMeta({ foo: 1 })).toBeNull();
  });

  it("returns null when meta is not an object", () => {
    expect(pickMeta({ meta: "str" })).toBeNull();
    expect(pickMeta({ meta: 42 })).toBeNull();
    expect(pickMeta({ meta: null })).toBeNull();
  });

  it("returns the meta object verbatim when present", () => {
    const meta = { source: "NSE", servedFrom: "ROTATION_ENGINE", asOf: "x" };
    expect(pickMeta({ meta, other: 1 })).toBe(meta);
  });
});

// ─── isMarketOpenIST ────────────────────────────────────────────────────────
describe("isMarketOpenIST", () => {
  // Build a Date that, when converted to IST, yields the given clock.
  // Mon = ISO weekday 1; Date.getDay() Mon = 1.
  function istClock(day: 0|1|2|3|4|5|6, hourIST: number, minuteIST = 0): Date {
    // 2026-05-04 is a Monday (UTC) — base = noon UTC that day.
    const baseSundayUtcMs = Date.UTC(2026, 4, 3, 0, 0, 0); // Sunday 2026-05-03 00:00 UTC
    const dayMs = day * 86_400_000;
    // IST = UTC + 5:30, so for an IST clock H:M on a given IST day, UTC is H-5, M-30.
    const utcHour    = hourIST - 5;
    const utcMinute  = minuteIST - 30;
    return new Date(baseSundayUtcMs + dayMs + utcHour * 3600_000 + utcMinute * 60_000);
  }

  it("returns false on Saturday/Sunday at all hours", () => {
    expect(isMarketOpenIST(istClock(0, 11))).toBe(false);   // Sun 11:00 IST
    expect(isMarketOpenIST(istClock(6, 11))).toBe(false);   // Sat 11:00 IST
  });

  it("returns true at 09:15 IST on a weekday (open boundary)", () => {
    expect(isMarketOpenIST(istClock(1, 9, 15))).toBe(true);
  });

  it("returns true at 15:30 IST on a weekday (close boundary)", () => {
    expect(isMarketOpenIST(istClock(1, 15, 30))).toBe(true);
  });

  it("returns false at 09:14 IST (one minute before open)", () => {
    expect(isMarketOpenIST(istClock(1, 9, 14))).toBe(false);
  });

  it("returns false at 15:31 IST (one minute after close)", () => {
    expect(isMarketOpenIST(istClock(1, 15, 31))).toBe(false);
  });

  it("returns true mid-session", () => {
    expect(isMarketOpenIST(istClock(2, 12, 0))).toBe(true);   // Tue noon
    expect(isMarketOpenIST(istClock(5, 14, 30))).toBe(true);  // Fri 2:30 PM
  });
});

// ─── marketDataQueryOptions ─────────────────────────────────────────────────
describe("marketDataQueryOptions", () => {
  const noop = async () => ({});

  it("attaches the query key and queryFn", () => {
    const opts = marketDataQueryOptions(["x"], noop);
    expect(opts.queryKey).toEqual(["x"]);
    expect(opts.queryFn).toBe(noop);
  });

  it("always re-validates on focus and reconnect", () => {
    const opts = marketDataQueryOptions(["x"], noop);
    expect(opts.refetchOnWindowFocus).toBe(true);
    expect(opts.refetchOnReconnect).toBe(true);
  });

  it("uses 60s cadence when market is open, 5min when closed", () => {
    const opts = marketDataQueryOptions(["x"], noop);
    // The function snapshots isMarketOpenIST() at call-time. Either branch
    // is valid, but the value must be one of the two documented cadences.
    expect([60_000, 5 * 60_000]).toContain(opts.staleTime);
    expect(opts.staleTime).toBe(opts.refetchInterval);
  });

  it("overrides win against defaults", () => {
    const opts = marketDataQueryOptions(["x"], noop, {
      staleTime: 999, refetchInterval: false as const,
    });
    expect(opts.staleTime).toBe(999);
    expect(opts.refetchInterval).toBe(false);
  });
});
