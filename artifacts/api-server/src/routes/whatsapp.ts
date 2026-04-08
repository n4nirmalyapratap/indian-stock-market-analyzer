import { Router, type Request, type Response } from "express";
import { SectorsService } from "../services/sectors.service.js";
import { StocksService } from "../services/stocks.service.js";
import { PatternsService } from "../services/patterns.service.js";
import { ScannersService } from "../services/scanners.service.js";
import { WhatsappService } from "../services/whatsapp.service.js";
import { NseService } from "../services/nse.service.js";
import { YahooService } from "../services/yahoo.service.js";

const router = Router();

let whatsappService: WhatsappService | null = null;
function getService() {
  if (!whatsappService) {
    const nse     = new NseService();
    const yahoo   = new YahooService();
    const sectors  = new SectorsService(nse, yahoo);
    const stocks   = new StocksService(nse, yahoo);
    const patterns = new PatternsService(yahoo, nse);
    const scanners = new ScannersService(yahoo, nse);
    whatsappService = new WhatsappService(sectors, stocks, patterns, scanners);
  }
  return whatsappService;
}

// ─── Simple in-memory rate limiter (per IP, per minute) ──────────────────────

const msgCounts = new Map<string, { count: number; resetAt: number }>();
const MSG_LIMIT = 10;

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const entry = msgCounts.get(ip);
  if (!entry || now > entry.resetAt) {
    msgCounts.set(ip, { count: 1, resetAt: now + 60_000 });
    return false;
  }
  entry.count += 1;
  if (entry.count > MSG_LIMIT) return true;
  return false;
}

// Periodically clean up stale rate-limit entries to avoid unbounded growth
setInterval(() => {
  const now = Date.now();
  for (const [k, v] of msgCounts) if (now > v.resetAt) msgCounts.delete(k);
}, 60_000).unref();

// ─── Routes ───────────────────────────────────────────────────────────────────

router.get("/status", (_req: Request, res: Response) => {
  res.json(getService().getBotStatus());
});

router.post("/message", async (req: Request, res: Response) => {
  const ip = (req.headers["x-forwarded-for"] as string | undefined)?.split(",")[0].trim()
    ?? req.socket.remoteAddress
    ?? "unknown";

  if (isRateLimited(ip)) {
    res.status(429).json({ error: "Too many requests. Please wait a minute." });
    return;
  }

  const { from, message } = req.body ?? {};
  if (!message || typeof message !== "string" || !message.trim()) {
    res.status(400).json({ error: "message field is required" });
    return;
  }

  try {
    const response = await getService().processMessage({ from: from ?? "web-user", message });
    res.json(response);
  } catch (err) {
    req.log.error({ err }, "Bot message processing failed");
    res.status(500).json({ error: "Failed to process message" });
  }
});

/** Twilio webhook — paste as "When a message comes in" URL in Twilio console */
router.post("/twilio", async (req: Request, res: Response) => {
  const body = req.body as Record<string, string>;
  const messageText = body.Body || body.body || "";
  const from        = body.From || body.from || "unknown";

  try {
    const result = await getService().processMessage({ from, message: messageText });
    const replyText = result.response || "No response";

    const escaped = replyText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

    res.set("Content-Type", "text/xml");
    res.send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>${escaped}</Message>
</Response>`);
  } catch (err) {
    req.log.error({ err }, "Twilio webhook failed");
    res.set("Content-Type", "text/xml");
    res.send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>Sorry, something went wrong. Please try again.</Message>
</Response>`);
  }
});

router.get("/messages", (_req: Request, res: Response) => {
  res.json(getService().getMessageLog());
});

router.post("/qr", (_req: Request, res: Response) => {
  res.json(getService().simulateQrCode());
});

router.put("/status", (req: Request, res: Response) => {
  const { enabled } = req.body ?? {};
  if (typeof enabled !== "boolean") {
    res.status(400).json({ error: "enabled must be a boolean" });
    return;
  }
  res.json(getService().updateBotStatus(enabled));
});

export default router;
