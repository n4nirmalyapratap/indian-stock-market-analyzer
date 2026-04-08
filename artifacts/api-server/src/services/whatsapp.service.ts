import { SectorsService } from "./sectors.service.js";
import { StocksService } from "./stocks.service.js";
import { PatternsService } from "./patterns.service.js";
import { ScannersService } from "./scanners.service.js";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Message { from: string; text: string; timestamp: string; response: string; }

// ─── Module-level state ───────────────────────────────────────────────────────

/** Ring-buffer: never grows beyond MAX_LOG entries */
const MAX_LOG = 200;
const messageLog: Message[] = [];

let botEnabled = true;
let sessionQr: string | null = null;
let sessionStatus = "DISCONNECTED";

// ─── Service ──────────────────────────────────────────────────────────────────

export class WhatsappService {
  constructor(
    private sectors: SectorsService,
    private stocks:  StocksService,
    private patterns: PatternsService,
    private scanners: ScannersService,
  ) {}

  getBotStatus() {
    return {
      status: botEnabled ? sessionStatus : "DISABLED",
      enabled: botEnabled,
      qrCode: sessionQr,
      sessionActive: sessionStatus === "CONNECTED",
      lastActive: messageLog.length > 0 ? messageLog[messageLog.length - 1].timestamp : null,
      totalMessages: messageLog.length,
      capabilities: [
        "Stock analysis", "Sector rotation", "Pattern scan", "Custom scanners", "Entry/exit signals",
      ],
      commands: [
        "!help","!sectors","!rotation","!analyze <SYMBOL>",
        "!patterns","!scan","!scanner list","!scanner run <id>",
        "!entry <SYMBOL>","!status",
      ],
    };
  }

  async processMessage(body: { from?: string; message?: string; text?: string }): Promise<{
    from: string; text: string; timestamp: string; response: string; processingTime: string;
  }> {
    const from = body.from || "unknown-user";
    const text = (body.message || body.text || "").trim();
    if (!text) throw new Error("No message text provided");

    const start = Date.now();
    let response = "";
    try {
      response = await this.route(text.toLowerCase(), text);
    } catch (e: unknown) {
      response = `Error processing command: ${e instanceof Error ? e.message : "Unknown error"}`;
    }

    const entry: Message = { from, text, timestamp: new Date().toISOString(), response };

    // Bounded ring-buffer
    messageLog.push(entry);
    if (messageLog.length > MAX_LOG) messageLog.splice(0, messageLog.length - MAX_LOG);

    return { ...entry, processingTime: `${Date.now() - start}ms` };
  }

  private async route(cmd: string, raw: string): Promise<string> {
    if (cmd === "!help"   || cmd === "help")   return this.help();
    if (cmd === "!status" || cmd === "status") return this.status();

    if (cmd.startsWith("!analyze ") || cmd.startsWith("analyze ")) {
      const sym = raw.split(" ")[1]?.toUpperCase();
      if (!sym) return "Usage: !analyze <SYMBOL>\nExample: !analyze RELIANCE";
      return this.analyzeStock(sym);
    }

    if (cmd === "!sectors"  || cmd === "sectors")  return this.fetchSectors();
    if (cmd === "!rotation" || cmd === "rotation") return this.fetchRotation();
    if (cmd === "!patterns" || cmd === "patterns") return this.fetchPatterns();
    if (cmd === "!scan")    return this.triggerScan();
    if (cmd === "!scanner list") return this.listScanners();

    if (cmd.startsWith("!scanner run ")) {
      const id = raw.split(" ")[2];
      return this.runScanner(id);
    }

    if (cmd.startsWith("!entry ") || cmd.startsWith("entry ")) {
      const sym = raw.split(" ")[1]?.toUpperCase();
      if (!sym) return "Usage: !entry <SYMBOL>";
      return this.entrySignal(sym);
    }

    return "Unknown command. Type !help for available commands.";
  }

  private help(): string {
    return `🤖 *Indian Stock Market Bot*\n\n*Commands:*\n!sectors — Sector performance overview\n!rotation — Sector rotation analysis\n!analyze <SYMBOL> — Full stock analysis\n!entry <SYMBOL> — Entry/exit signal\n!patterns — Chart patterns (CALL/PUT signals)\n!scan — Trigger fresh pattern scan\n!scanner list — List custom scanners\n!scanner run <id> — Run a scanner\n!status — Bot status\n!help — This help message\n\n_End-of-day data. Not real-time._`;
  }

  private status(): string {
    return `*Bot Status:* ${botEnabled ? "✅ Active" : "❌ Disabled"}\n*Session:* ${sessionStatus}\n*Messages Processed:* ${messageLog.length}`;
  }

  private async fetchSectors(): Promise<string> {
    const data = await this.sectors.getAllSectors();
    if (!data?.length) return "Sector data unavailable right now.";

    // Use .slice().sort() to avoid mutating the original array
    const sorted   = [...data].sort((a, b) => b.pChange - a.pChange);
    const top5     = sorted.slice(0, 5);
    const bottom3  = sorted.slice(-3).reverse();

    let msg = "📊 *Sector Overview*\n\n*Top Gainers:*\n";
    top5.forEach(s => { msg += `• ${s.name}: ${s.pChange > 0 ? "+" : ""}${s.pChange?.toFixed(2) ?? 0}%\n`; });
    msg += "\n*Laggards:*\n";
    bottom3.forEach(s => { msg += `• ${s.name}: ${s.pChange?.toFixed(2) ?? 0}%\n`; });
    return msg;
  }

  private async fetchRotation(): Promise<string> {
    const r = await this.sectors.getSectorRotation();
    if (!r) return "Sector rotation data unavailable right now.";
    let msg = `🔄 *Sector Rotation Analysis*\n\n*Phase:* ${r.rotationPhase}\n\n*Market Breadth:*\n• Advancing: ${r.marketBreadth.advancing}\n• Declining: ${r.marketBreadth.declining}\n\n*Where to Buy Now:*\n`;
    (r.whereToBuyNow ?? []).slice(0, 5).forEach((s: { name: string }) => { msg += `• ${s.name}\n`; });
    msg += `\n_${r.recommendation}_`;
    return msg;
  }

  private async analyzeStock(symbol: string): Promise<string> {
    const d = await this.stocks.getStockDetails(symbol);
    if (d.error) return `❌ ${d.error}`;
    const ta = d.technicalAnalysis;
    let msg = `📈 *${d.companyName || symbol}* (${symbol})\n`;
    msg += `💰 Price: ₹${d.lastPrice?.toFixed(2) ?? "N/A"}\n`;
    msg += `📊 Change: ${d.pChange > 0 ? "+" : ""}${d.pChange?.toFixed(2) ?? 0}%\n`;
    if (ta) {
      msg += `\n*Technical Analysis:*\n`;
      msg += `• Trend: ${ta.trend}\n`;
      msg += `• RSI(14): ${ta.rsi?.toFixed(1)} — ${ta.rsiZone}\n`;
      msg += `• MACD: ${ta.macd?.crossover}\n`;
      if (ta.nearestSupport)    msg += `• Support: ₹${ta.nearestSupport?.toFixed(2)}\n`;
      if (ta.nearestResistance) msg += `• Resistance: ₹${ta.nearestResistance?.toFixed(2)}\n`;
    }
    if (d.entryRecommendation) {
      const er = d.entryRecommendation;
      msg += `\n*Entry Signal:* ${er.entryCall}\n_${er.summary}_`;
    }
    return msg;
  }

  private async fetchPatterns(): Promise<string> {
    const d = await this.patterns.getPatterns();
    if (!d.patterns?.length) return "No patterns detected currently. Try !scan to refresh.";
    let msg = `🕯️ *Chart Patterns* (${new Date(d.lastScanTime).toLocaleDateString()})\n\n*CALL Signals (${d.callSignals}):*\n`;
    (d.topCalls ?? []).slice(0, 5).forEach((p: { symbol: string; pattern: string; confidence: number }) => {
      msg += `• ${p.symbol} — ${p.pattern} (${p.confidence}%)\n`;
    });
    msg += `\n*PUT Signals (${d.putSignals}):*\n`;
    (d.topPuts ?? []).slice(0, 3).forEach((p: { symbol: string; pattern: string; confidence: number }) => {
      msg += `• ${p.symbol} — ${p.pattern} (${p.confidence}%)\n`;
    });
    return msg;
  }

  private async triggerScan(): Promise<string> {
    const d = await this.patterns.triggerScan();
    const top = (d.patterns ?? []).slice(0, 5).map((p: { symbol: string; pattern: string }) => `• ${p.symbol}: ${p.pattern}`).join("\n");
    return `🔍 *Scan Complete*\n• Total Patterns: ${d.totalFound}\n• CALL Signals: ${d.callSignals}\n• PUT Signals: ${d.putSignals}\n\nTop results:\n${top || "None"}`;
  }

  private listScanners(): string {
    const all = this.scanners.getAllScanners();
    if (all.length === 0) return "No custom scanners defined.";
    let msg = "🔎 *Custom Scanners:*\n";
    all.forEach(s => { msg += `• *${s.id}:* ${s.name}\n`; });
    msg += "\nUse: !scanner run <id>";
    return msg;
  }

  private async runScanner(id: string): Promise<string> {
    if (!id) return "Usage: !scanner run <id>";
    const r = await this.scanners.runScanner(id);
    if ("error" in r) return `❌ ${r.error}`;
    const top = (r.results ?? []).slice(0, 8)
      .map((s: { symbol: string; lastPrice: number }) => `• ${s.symbol} ₹${s.lastPrice?.toFixed(2)}`)
      .join("\n") || "No matches found";
    return `🔎 *${r.scannerName}*\n• Scanned: ${r.totalScanned}\n• Matched: ${r.totalMatched}\n\nTop results:\n${top}`;
  }

  private async entrySignal(symbol: string): Promise<string> {
    const d = await this.stocks.getStockDetails(symbol);
    if (d.error) return `❌ ${d.error}`;
    const er = d.entryRecommendation;
    if (!er) return `Unable to generate entry signal for ${symbol}`;
    return `🎯 *Entry Signal: ${symbol}*\n\n*Signal:* ${er.entryCall}\n*Confidence:* ${er.confidence}\n${er.targetPrice ? `*Target:* ₹${er.targetPrice?.toFixed(2)}\n` : ""}${er.stopLoss ? `*Stop Loss:* ₹${er.stopLoss?.toFixed(2)}\n` : ""}${er.riskReward ? `*R:R Ratio:* ${er.riskReward}:1\n` : ""}\n_${er.summary}_`;
  }

  getMessageLog(): Message[] {
    return messageLog.slice(-50);
  }

  simulateQrCode() {
    sessionQr = `SIMULATED_QR_${Date.now()}`;
    sessionStatus = "WAITING_FOR_QR_SCAN";
    return { qrCode: sessionQr, status: sessionStatus, message: "Scan with WhatsApp to connect" };
  }

  updateBotStatus(enabled: boolean) {
    botEnabled = enabled;
    return { enabled, status: botEnabled ? sessionStatus : "DISABLED" };
  }
}
