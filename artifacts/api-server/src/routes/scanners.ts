import { Router, type Request, type Response } from "express";
import { YahooService } from "../services/yahoo.service.js";
import { NseService } from "../services/nse.service.js";
import { ScannersService } from "../services/scanners.service.js";

const router = Router();
let svc: ScannersService | null = null;
function getSvc() {
  if (!svc) svc = new ScannersService(new YahooService(), new NseService());
  return svc;
}

// ─── Input validation ─────────────────────────────────────────────────────────

const VALID_LOGIC = new Set(["AND", "OR"]);
const VALID_OPERATORS = new Set([
  "gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below",
]);
const VALID_UNIVERSES = new Set(["NIFTY100", "MIDCAP", "SMALLCAP"]);

function validateScannerBody(body: unknown): string | null {
  if (!body || typeof body !== "object") return "Request body must be a JSON object";

  const b = body as Record<string, unknown>;

  if (!b.name || typeof b.name !== "string" || !b.name.trim())
    return "Scanner name is required";
  if (b.name.length > 100)
    return "Scanner name must be ≤ 100 characters";
  if (b.description && typeof b.description !== "string")
    return "Description must be a string";

  if (!Array.isArray(b.universe) || b.universe.length === 0)
    return "At least one universe is required (NIFTY100 | MIDCAP | SMALLCAP)";
  for (const u of b.universe as unknown[]) {
    if (!VALID_UNIVERSES.has(u as string))
      return `Invalid universe value: "${u}". Must be NIFTY100, MIDCAP, or SMALLCAP`;
  }

  if (b.logic && !VALID_LOGIC.has(b.logic as string))
    return `Logic must be "AND" or "OR"`;

  if (!Array.isArray(b.conditions) || b.conditions.length === 0)
    return "At least one condition is required";
  if (b.conditions.length > 20)
    return "A scanner may have at most 20 conditions";

  for (const c of b.conditions as unknown[]) {
    if (!c || typeof c !== "object") return "Each condition must be an object";
    const cond = c as Record<string, unknown>;
    if (!VALID_OPERATORS.has(cond.operator as string))
      return `Invalid operator: "${cond.operator}"`;
    if (!cond.left || typeof cond.left !== "object") return "Condition must have a left side";
    if (!cond.right || typeof cond.right !== "object") return "Condition must have a right side";
  }

  return null;
}

// ─── Routes ───────────────────────────────────────────────────────────────────

router.get("/", (_req: Request, res: Response) => {
  res.json(getSvc().getAllScanners());
});

// IMPORTANT: literal sub-paths must be defined before /:id
router.post("/adhoc/run", async (req: Request, res: Response) => {
  const err = validateScannerBody(req.body);
  if (err) { res.status(400).json({ error: err }); return; }
  try {
    res.json(await getSvc().runAdHoc(req.body));
  } catch (e: unknown) {
    req.log.error({ err: e }, "Ad-hoc scan failed");
    res.status(500).json({ error: "Ad-hoc scan failed" });
  }
});

router.get("/:id", (req: Request, res: Response) => {
  const id = String(req.params.id ?? "").trim();
  if (!id) { res.status(400).json({ error: "Scanner id is required" }); return; }
  const s = getSvc().getScannerById(id);
  if (!s) { res.status(404).json({ error: "Scanner not found" }); return; }
  res.json(s);
});

router.post("/", (req: Request, res: Response) => {
  const err = validateScannerBody(req.body);
  if (err) { res.status(400).json({ error: err }); return; }
  res.status(201).json(getSvc().createScanner(req.body));
});

router.put("/:id", (req: Request, res: Response) => {
  const id = String(req.params.id ?? "").trim();
  if (!id) { res.status(400).json({ error: "Scanner id is required" }); return; }
  const err = validateScannerBody(req.body);
  if (err) { res.status(400).json({ error: err }); return; }
  const s = getSvc().updateScanner(id, req.body);
  if (!s) { res.status(404).json({ error: "Scanner not found" }); return; }
  res.json(s);
});

router.delete("/:id", (req: Request, res: Response) => {
  const id = String(req.params.id ?? "").trim();
  if (!id) { res.status(400).json({ error: "Scanner id is required" }); return; }
  const ok = getSvc().deleteScanner(id);
  if (!ok) { res.status(404).json({ error: "Scanner not found" }); return; }
  res.json({ success: true });
});

router.post("/:id/run", async (req: Request, res: Response) => {
  const id = String(req.params.id ?? "").trim();
  if (!id) { res.status(400).json({ error: "Scanner id is required" }); return; }
  try {
    const result = await getSvc().runScanner(id);
    if ("error" in result) { res.status(404).json(result); return; }
    res.json(result);
  } catch (e: unknown) {
    req.log.error({ err: e }, "Scanner run failed");
    res.status(500).json({ error: "Scanner run failed" });
  }
});

export default router;
