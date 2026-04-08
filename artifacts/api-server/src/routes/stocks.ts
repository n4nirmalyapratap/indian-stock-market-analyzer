import { Router, type Request, type Response } from "express";
import { NseService } from "../services/nse.service.js";
import { YahooService } from "../services/yahoo.service.js";
import { StocksService } from "../services/stocks.service.js";

const router = Router();
let stocksService: StocksService | null = null;
function getService() {
  if (!stocksService) stocksService = new StocksService(new NseService(), new YahooService());
  return stocksService;
}

// ─── Symbol sanitisation ──────────────────────────────────────────────────────

/** Accept alphanumerics, dash, ampersand, period — up to 30 chars. */
const SYMBOL_RE = /^[A-Z0-9&.\-]{1,30}$/;

function sanitizeSymbol(raw: string): string | null {
  const s = raw.trim().toUpperCase();
  return SYMBOL_RE.test(s) ? s : null;
}

// ─── Routes ───────────────────────────────────────────────────────────────────

router.get("/nifty100", async (req: Request, res: Response) => {
  try {
    res.json(await getService().getNifty100Stocks());
  } catch (err) {
    req.log.error({ err }, "Failed to get nifty100");
    res.status(500).json({ error: "Failed to fetch Nifty 100 stocks" });
  }
});

router.get("/midcap", async (req: Request, res: Response) => {
  try {
    res.json(await getService().getMidcapStocks());
  } catch (err) {
    req.log.error({ err }, "Failed to get midcap");
    res.status(500).json({ error: "Failed to fetch Midcap stocks" });
  }
});

router.get("/smallcap", async (req: Request, res: Response) => {
  try {
    res.json(await getService().getSmallcapStocks());
  } catch (err) {
    req.log.error({ err }, "Failed to get smallcap");
    res.status(500).json({ error: "Failed to fetch Smallcap stocks" });
  }
});

router.get("/:symbol", async (req: Request, res: Response) => {
  const symbol = sanitizeSymbol(String(req.params.symbol ?? ""));
  if (!symbol) {
    res.status(400).json({ error: "Invalid symbol. Use uppercase letters, digits, dash, or ampersand (max 30 chars)." });
    return;
  }
  try {
    const data = await getService().getStockDetails(symbol);
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to get stock details");
    res.status(500).json({ error: "Failed to fetch stock data" });
  }
});

export default router;
