/**
 * chart-geometry.test.ts
 * ──────────────────────
 * Deep tests for the pure geometry helpers used by Chart Studio's drawing
 * layer. These functions are the floor under every drawing tool — line/ray
 * extension and hit-testing — so a regression here means drawings render
 * in the wrong place or refuse to be selected.
 */
import { describe, it, expect } from "vitest";
import {
  computeHA,
  extendRay,
  distToSegment,
  distToRect,
  type Candle,
} from "../ChartPanel";

// ─── helpers ────────────────────────────────────────────────────────────────

function bar(o: number, h: number, l: number, c: number, t = 0): Candle {
  return { time: t, open: o, high: h, low: l, close: c, volume: 1_000 };
}

const BOX = { x0: 0, y0: 0, x1: 1000, y1: 800 } as const;
function ray(px: number, py: number, nx: number, ny: number) {
  return extendRay(px, py, nx, ny, BOX.x0, BOX.y0, BOX.x1, BOX.y1);
}

// ─── computeHA ───────────────────────────────────────────────────────────────
describe("computeHA (Heikin-Ashi transform)", () => {
  it("first bar's HA-open is the average of the first bar's real open & close", () => {
    const cs = [bar(100, 110, 90, 108)];
    const ha = computeHA(cs);
    expect(ha).toHaveLength(1);
    expect(ha[0].open).toBeCloseTo((100 + 108) / 2, 6);
  });

  it("HA-close is always the OHLC4 of the matching real bar", () => {
    const cs = [bar(100, 110, 90, 108), bar(108, 120, 105, 115)];
    const ha = computeHA(cs);
    expect(ha[0].close).toBeCloseTo((100 + 110 + 90 + 108) / 4, 6);
    expect(ha[1].close).toBeCloseTo((108 + 120 + 105 + 115) / 4, 6);
  });

  it("subsequent HA-open is the midpoint of the PREVIOUS HA bar's open/close", () => {
    const cs = [bar(100, 110, 90, 108), bar(108, 120, 105, 115)];
    const ha = computeHA(cs);
    const expectedOpen2 = (ha[0].open + ha[0].close) / 2;
    expect(ha[1].open).toBeCloseTo(expectedOpen2, 6);
  });

  it("HA-high ≥ max(real high, HA-open, HA-close) for every bar", () => {
    const cs = [bar(100, 110, 90, 108), bar(108, 120, 105, 115), bar(115, 130, 112, 128)];
    const ha = computeHA(cs);
    ha.forEach((h, i) => {
      expect(h.high).toBeGreaterThanOrEqual(cs[i].high);
      expect(h.high).toBeGreaterThanOrEqual(h.open);
      expect(h.high).toBeGreaterThanOrEqual(h.close);
    });
  });

  it("HA-low ≤ min(real low, HA-open, HA-close) for every bar", () => {
    const cs = [bar(100, 110, 90, 108), bar(108, 120, 105, 115), bar(115, 130, 112, 128)];
    const ha = computeHA(cs);
    ha.forEach((h, i) => {
      expect(h.low).toBeLessThanOrEqual(cs[i].low);
      expect(h.low).toBeLessThanOrEqual(h.open);
      expect(h.low).toBeLessThanOrEqual(h.close);
    });
  });

  it("preserves time and volume verbatim", () => {
    const cs = [bar(100, 110, 90, 108, 111), bar(108, 120, 105, 115, 222)];
    const ha = computeHA(cs);
    expect(ha[0].time).toBe(111);
    expect(ha[1].time).toBe(222);
    expect(ha[0].volume).toBe(1_000);
  });

  it("strong uptrend → all bars are bullish (HA-close ≥ HA-open)", () => {
    const cs = [];
    let p = 100;
    for (let i = 0; i < 20; i++) {
      cs.push(bar(p, p + 8, p - 1, p + 6));
      p += 6;
    }
    const ha = computeHA(cs);
    // Allow the first 1-2 bars to be transitional, then expect persistence.
    const tail = ha.slice(3);
    expect(tail.every(h => h.close >= h.open)).toBe(true);
  });

  it("strong downtrend → all bars are bearish (HA-close ≤ HA-open)", () => {
    const cs = [];
    let p = 200;
    for (let i = 0; i < 20; i++) {
      cs.push(bar(p, p + 1, p - 8, p - 6));
      p -= 6;
    }
    const ha = computeHA(cs);
    const tail = ha.slice(3);
    expect(tail.every(h => h.close <= h.open)).toBe(true);
  });

  it("empty input returns empty output", () => {
    expect(computeHA([])).toEqual([]);
  });

  it("does not mutate the input candles", () => {
    const cs = [bar(100, 110, 90, 108)];
    const snapshot = JSON.stringify(cs);
    computeHA(cs);
    expect(JSON.stringify(cs)).toBe(snapshot);
  });
});

// ─── extendRay ───────────────────────────────────────────────────────────────
describe("extendRay (extend a ray to the box edge)", () => {
  it("extends to the right edge for a horizontal eastward ray", () => {
    const [x, y] = ray(100, 400, 1, 0);
    expect(x).toBeCloseTo(1000, 6);
    expect(y).toBeCloseTo(400, 6);
  });

  it("extends to the left edge for a horizontal westward ray", () => {
    const [x, y] = ray(500, 400, -1, 0);
    expect(x).toBeCloseTo(0, 6);
    expect(y).toBeCloseTo(400, 6);
  });

  it("extends to the top edge for a vertical upward ray", () => {
    const [x, y] = ray(500, 600, 0, -1);
    expect(x).toBeCloseTo(500, 6);
    expect(y).toBeCloseTo(0, 6);
  });

  it("extends to the bottom edge for a vertical downward ray", () => {
    const [x, y] = ray(500, 100, 0, 1);
    expect(x).toBeCloseTo(500, 6);
    expect(y).toBeCloseTo(800, 6);
  });

  it("stops at whichever edge is hit first for a diagonal ray", () => {
    // From (0,0) at 45° down-right, the box (1000x800) is hit at the bottom
    // edge (y=800) first because 800 < 1000.
    const [x, y] = ray(0, 0, 1, 1);
    expect(y).toBeCloseTo(800, 6);
    expect(x).toBeCloseTo(800, 6);
  });

  it("works for non-unit direction vectors (only direction matters)", () => {
    const [x, y]   = ray(100, 400, 5, 0);
    const [x2, y2] = ray(100, 400, 1, 0);
    expect(x).toBeCloseTo(x2, 6);
    expect(y).toBeCloseTo(y2, 6);
  });

  it("returned point lies on the original ray (px+t*nx, py+t*ny)", () => {
    const [x, y] = ray(200, 300, 2, 1);
    // Vector from origin: (x-200, y-300) must be parallel to (2, 1)
    const t = (x - 200) / 2;
    expect(y - 300).toBeCloseTo(t * 1, 4);
    expect(t).toBeGreaterThan(0); // forward direction
  });

  it("the returned endpoint always lands on at least one box edge", () => {
    // Endpoint must satisfy x∈{x0,x1} OR y∈{y0,y1} (≈ within float error).
    const inputs: [number, number, number, number][] = [
      [100, 400,  1,  0], [500, 400, -1,  0],
      [500, 600,  0, -1], [500, 100,  0,  1],
      [0,   0,    1,  1], [200, 300,  2,  1],
      [123, 456,  3,  -2], [777, 111, -1,  3],
    ];
    for (const [px, py, nx, ny] of inputs) {
      const [x, y] = ray(px, py, nx, ny);
      const onEdge =
        Math.abs(x - BOX.x0) < 1e-6 || Math.abs(x - BOX.x1) < 1e-6 ||
        Math.abs(y - BOX.y0) < 1e-6 || Math.abs(y - BOX.y1) < 1e-6;
      expect(onEdge).toBe(true);
      // And the endpoint stays within the box on the other axis.
      expect(x).toBeGreaterThanOrEqual(BOX.x0 - 1e-6);
      expect(x).toBeLessThanOrEqual(BOX.x1 + 1e-6);
      expect(y).toBeGreaterThanOrEqual(BOX.y0 - 1e-6);
      expect(y).toBeLessThanOrEqual(BOX.y1 + 1e-6);
    }
  });

  it("a ray from a point already ON an outward edge does not move backward", () => {
    // Sitting on the right edge (x=1000), pointing further right.
    // Forward t along (+x) is 0, so the endpoint should equal the start.
    const [x, y] = ray(1000, 400, 1, 0);
    expect(x).toBeCloseTo(1000, 6);
    expect(y).toBeCloseTo(400, 6);
  });
});

// ─── distToSegment ───────────────────────────────────────────────────────────
describe("distToSegment", () => {
  it("zero distance for a point exactly on the segment", () => {
    expect(distToSegment(50, 50, 0, 0, 100, 100)).toBeCloseTo(0, 6);
    expect(distToSegment(0,  0,  0, 0, 100, 100)).toBeCloseTo(0, 6);
    expect(distToSegment(100, 100, 0, 0, 100, 100)).toBeCloseTo(0, 6);
  });

  it("perpendicular distance for a point off the middle of a horizontal segment", () => {
    expect(distToSegment(50, 25, 0, 0, 100, 0)).toBe(25);
  });

  it("clamps to the nearer endpoint when the foot of perpendicular is outside the segment", () => {
    // Segment along x=0..10 at y=0; point at (-5, 5). Foot of perp at x=-5
    // is OUTSIDE the segment, so distance = euclidean to (0,0).
    expect(distToSegment(-5, 5, 0, 0, 10, 0)).toBeCloseTo(Math.hypot(5, 5), 6);
    // Symmetric on the right side
    expect(distToSegment(15, 5, 0, 0, 10, 0)).toBeCloseTo(Math.hypot(5, 5), 6);
  });

  it("zero-length segment behaves like distance to the single point", () => {
    expect(distToSegment(3, 4, 0, 0, 0, 0)).toBe(5);
  });

  it("is symmetric under swap of endpoints", () => {
    const d1 = distToSegment(7, 3, 0, 0, 10, 10);
    const d2 = distToSegment(7, 3, 10, 10, 0, 0);
    expect(d1).toBeCloseTo(d2, 6);
  });

  it("never returns NaN or negative", () => {
    const cases: [number, number, number, number, number, number][] = [
      [0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 1, 1], [-3, -4, 0, 0, 0, 0],
      [50, -50, 100, 100, 200, 200],
    ];
    for (const c of cases) {
      const d = distToSegment(...c);
      expect(d).toBeGreaterThanOrEqual(0);
      expect(Number.isFinite(d)).toBe(true);
    }
  });
});

// ─── distToRect ──────────────────────────────────────────────────────────────
describe("distToRect", () => {
  // Rect at (10,20) size 100x50 → spans x=[10,110], y=[20,70]
  it("zero-edged distance just outside each face", () => {
    expect(distToRect(5,  45, 10, 20, 100, 50)).toBe(5);   // left of x=10
    expect(distToRect(120, 45, 10, 20, 100, 50)).toBe(10); // right of x=110
    expect(distToRect(60, 10, 10, 20, 100, 50)).toBe(10);  // above y=20
    expect(distToRect(60, 100, 10, 20, 100, 50)).toBe(30); // below y=70
  });

  it("euclidean distance to nearest corner when outside on both axes", () => {
    // Top-left corner at (10,20); point at (4,12) → dist = √(6²+8²) = 10
    expect(distToRect(4, 12, 10, 20, 100, 50)).toBeCloseTo(10, 6);
  });

  it("returns the distance to the NEAREST edge when point is INSIDE", () => {
    // Point (15,40): dist to left=5, top=20, right=95, bottom=30 → min=5
    expect(distToRect(15, 40, 10, 20, 100, 50)).toBe(5);
    // Centre (60,45) → equidistant to top(25)/bottom(25), left(50)/right(50)
    expect(distToRect(60, 45, 10, 20, 100, 50)).toBe(25);
  });

  it("zero on every corner and edge", () => {
    expect(distToRect(10, 20,  10, 20, 100, 50)).toBe(0);   // top-left corner
    expect(distToRect(110, 20, 10, 20, 100, 50)).toBe(0);   // top-right
    expect(distToRect(10, 70,  10, 20, 100, 50)).toBe(0);   // bottom-left
    expect(distToRect(110, 70, 10, 20, 100, 50)).toBe(0);   // bottom-right
    expect(distToRect(60, 20,  10, 20, 100, 50)).toBe(0);   // top edge
  });

  it("never returns NaN, Infinity, or negative", () => {
    const cases: [number, number, number, number, number, number][] = [
      [0, 0, 0, 0, 0, 0],
      [50, 50, 0, 0, 100, 100],
      [-100, -100, 0, 0, 1, 1],
      [10000, 10000, -50, -50, 25, 25],
    ];
    for (const c of cases) {
      const d = distToRect(...c);
      expect(d).toBeGreaterThanOrEqual(0);
      expect(Number.isFinite(d)).toBe(true);
    }
  });
});
