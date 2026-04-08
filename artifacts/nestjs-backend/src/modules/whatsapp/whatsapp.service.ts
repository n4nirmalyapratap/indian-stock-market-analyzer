import { Injectable, Logger } from '@nestjs/common';
import { SectorsService } from '../sectors/sectors.service';
import { StocksService } from '../stocks/stocks.service';
import { PatternsService } from '../patterns/patterns.service';
import { ScannersService } from '../scanners/scanners.service';

export interface BotMessage {
  from: string;
  body: string;
  timestamp: string;
}

export interface BotResponse {
  message: string;
  type: 'text' | 'list';
}

@Injectable()
export class WhatsappService {
  private readonly logger = new Logger(WhatsappService.name);
  private qrCodeData: string | null = null;
  private isConnected: boolean = false;
  private botEnabled: boolean = true;
  private sessionData: any = null;
  private messageLog: Array<{ message: BotMessage; response: string; timestamp: string }> = [];

  constructor(
    private readonly sectorsService: SectorsService,
    private readonly stocksService: StocksService,
    private readonly patternsService: PatternsService,
    private readonly scannersService: ScannersService,
  ) {}

  getBotStatus(): any {
    return {
      isConnected: this.isConnected,
      botEnabled: this.botEnabled,
      qrCodeAvailable: !!this.qrCodeData,
      qrCode: this.qrCodeData,
      messageCount: this.messageLog.length,
      lastActivity: this.messageLog[this.messageLog.length - 1]?.timestamp || null,
      capabilities: [
        '/sectors — Get all sector performance and rotation analysis',
        '/rotation — Which sectors to focus on today',
        '/patterns — Chart patterns detected (CALL/PUT signals)',
        '/scan [scanner-id] — Run a custom scanner',
        '[SYMBOL] — Get full stock analysis (e.g. RELIANCE, TCS)',
        '/help — Show this help menu',
      ],
    };
  }

  async processMessage(message: BotMessage): Promise<BotResponse> {
    const body = message.body.trim().toUpperCase();
    this.logger.log(`Processing message from ${message.from}: "${body}"`);

    let response = '';

    try {
      if (body === '/HELP' || body === 'HELP') {
        response = this.getHelpMessage();
      } else if (body === '/SECTORS' || body === 'SECTORS') {
        response = await this.getSectorSummary();
      } else if (body === '/ROTATION' || body === 'ROTATION') {
        response = await this.getRotationSummary();
      } else if (body.startsWith('/PATTERNS') || body === 'PATTERNS') {
        const parts = body.split(' ');
        const filter = parts[1] || '';
        response = await this.getPatternsSummary(filter);
      } else if (body.startsWith('/SCAN')) {
        const scannerId = body.split(' ')[1];
        response = await this.runScannerResponse(scannerId);
      } else if (body.startsWith('/SCANNERS') || body === 'SCANNERS') {
        response = this.getScannersList();
      } else if (body.startsWith('/FII') || body === 'FII') {
        response = 'FII/DII data is fetched from NSE. Please check /sectors for market breadth info.';
      } else if (body.length >= 2 && body.length <= 15 && /^[A-Z0-9&-]+$/.test(body) && !body.startsWith('/')) {
        response = await this.getStockSummary(body);
      } else {
        response = `I didn't understand that. Send /help to see all commands.`;
      }
    } catch (err) {
      this.logger.error(`Error processing message: ${err.message}`);
      response = `Sorry, there was an error processing your request. Please try again.`;
    }

    this.messageLog.push({ message, response, timestamp: new Date().toISOString() });
    if (this.messageLog.length > 1000) this.messageLog.shift();

    return { message: response, type: 'text' };
  }

  private getHelpMessage(): string {
    return `*Indian Stock Market Bot* 🇮🇳📈

*Commands:*
• /sectors — All sector performance
• /rotation — Sector rotation & focus areas
• /patterns — Chart pattern signals
• /patterns CALL — Only bullish signals
• /patterns PUT — Only bearish signals
• /scanners — List all saved scanners
• /scan [id] — Run a scanner

*Stock Analysis:*
• Just type any NSE symbol
• Example: RELIANCE
• Example: TCS, INFY, HDFCBANK

All data is end-of-day from NSE/Yahoo Finance.
Built for Indian market analysis 🚀`;
  }

  private async getSectorSummary(): Promise<string> {
    const sectors = await this.sectorsService.getAllSectors();
    const top5 = sectors.slice(0, 5);
    const bottom3 = sectors.slice(-3);

    let msg = `*Sector Performance Today* 📊\n\n`;
    msg += `*Top Performers:*\n`;
    top5.forEach(s => {
      const emoji = s.pChange > 0 ? '🟢' : '🔴';
      msg += `${emoji} ${s.name}: ${s.pChange > 0 ? '+' : ''}${(s.pChange || 0).toFixed(2)}%\n`;
    });
    msg += `\n*Laggards:*\n`;
    bottom3.forEach(s => {
      const emoji = s.pChange > 0 ? '🟢' : '🔴';
      msg += `${emoji} ${s.name}: ${s.pChange > 0 ? '+' : ''}${(s.pChange || 0).toFixed(2)}%\n`;
    });
    msg += `\n_Last updated: ${new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })} IST_`;
    return msg;
  }

  private async getRotationSummary(): Promise<string> {
    const rotation = await this.sectorsService.getSectorRotation();

    let msg = `*Sector Rotation Analysis* 🔄\n\n`;
    msg += `*Phase:* ${rotation.rotationPhase}\n\n`;
    msg += `*Focus Now (Buy These):*\n`;
    rotation.whereToBuyNow?.slice(0, 3).forEach((s: any) => {
      msg += `✅ ${s.name} (${(s.pChange || 0).toFixed(2)}%)\n`;
    });
    msg += `\n*Money Flowing Into:*\n`;
    rotation.currentlyFocused?.forEach((name: string) => {
      msg += `📈 ${name}\n`;
    });
    msg += `\n*Market Breadth:*\n`;
    msg += `🟢 Advancing: ${rotation.marketBreadth?.advancing} | 🔴 Declining: ${rotation.marketBreadth?.declining}\n`;
    msg += `\n*Recommendation:*\n${rotation.recommendation}`;
    return msg;
  }

  private async getPatternsSummary(filter: string): Promise<string> {
    const data = await this.patternsService.getPatterns(undefined, filter || undefined);
    const patterns = data.patterns?.slice(0, 8) || [];

    if (patterns.length === 0) {
      return `No chart patterns detected yet. Try running /scan first or wait for the scheduled scan.`;
    }

    let msg = `*Chart Pattern Alerts* 📉📈\n`;
    msg += `Total: ${data.totalPatterns} | CALL: ${data.callSignals} | PUT: ${data.putSignals}\n\n`;

    patterns.forEach((p: any) => {
      const emoji = p.signal === 'CALL' ? '🟢' : p.signal === 'PUT' ? '🔴' : '⚪';
      msg += `${emoji} *${p.symbol}* — ${p.pattern}\n`;
      msg += `   Signal: ${p.signal} | Confidence: ${p.confidence}%\n`;
      msg += `   Price: ₹${p.currentPrice?.toFixed(2)}\n\n`;
    });

    msg += `_Scan Time: ${new Date(data.lastScanTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST_`;
    return msg;
  }

  private async getStockSummary(symbol: string): Promise<string> {
    const stock = await this.stocksService.getStockDetails(symbol);

    if (stock.error) {
      return `❌ Stock "${symbol}" not found. Check the NSE symbol and try again.`;
    }

    let msg = `*${stock.companyName || symbol}* (${symbol})\n\n`;
    msg += `💰 *Price:* ₹${stock.lastPrice?.toFixed(2) || stock.technicalAnalysis?.currentPrice?.toFixed(2) || 'N/A'}\n`;

    const change = stock.change || 0;
    const pChange = stock.pChange || 0;
    const changeEmoji = pChange >= 0 ? '🟢' : '🔴';
    msg += `${changeEmoji} *Change:* ${pChange >= 0 ? '+' : ''}${pChange.toFixed(2)}% (₹${change >= 0 ? '+' : ''}${change.toFixed(2)})\n`;

    if (stock.technicalAnalysis) {
      const ta = stock.technicalAnalysis;
      msg += `\n*Technical Indicators:*\n`;
      msg += `📊 RSI(14): ${ta.rsi?.toFixed(1)} — ${ta.rsiZone}\n`;
      msg += `📈 Trend: ${ta.trend?.replace(/_/g, ' ')}\n`;
      msg += `🎯 MACD: ${ta.macd?.crossover}\n`;

      if (ta.nearestSupport) msg += `🛡 Support: ₹${ta.nearestSupport.toFixed(2)}\n`;
      if (ta.nearestResistance) msg += `🎯 Resistance: ₹${ta.nearestResistance.toFixed(2)}\n`;
    }

    if (stock.entryRecommendation) {
      const rec = stock.entryRecommendation;
      const recEmoji = rec.entryCall === 'ENTRY_CALL' ? '🟢' : rec.entryCall === 'ENTRY_PUT' ? '🔴' : '⚠️';
      msg += `\n*Entry Recommendation:*\n`;
      msg += `${recEmoji} ${rec.summary}\n`;
      if (rec.targetPrice) msg += `🎯 Target: ₹${rec.targetPrice.toFixed(2)}\n`;
      if (rec.stopLoss) msg += `🛡 Stop Loss: ₹${rec.stopLoss.toFixed(2)}\n`;
      if (rec.riskReward) msg += `📐 Risk:Reward = 1:${rec.riskReward}\n`;
    }

    if (stock.insight) {
      msg += `\n*Analysis:*\n${stock.insight}\n`;
    }

    msg += `\n_Data: NSE/Yahoo Finance | End-of-Day_`;
    return msg;
  }

  private getScannersList(): string {
    const scanners = this.scannersService.getAllScanners();
    let msg = `*Saved Scanners:*\n\n`;
    scanners.forEach(s => {
      msg += `📋 *${s.name}*\n`;
      msg += `   ID: ${s.id}\n`;
      msg += `   ${s.description || ''}\n\n`;
    });
    msg += `To run: /scan [scanner-id]`;
    return msg;
  }

  private async runScannerResponse(scannerId: string): Promise<string> {
    if (!scannerId) {
      return `Please provide a scanner ID. Use /scanners to see all available scanners.`;
    }

    const result = await this.scannersService.runScanner(scannerId);
    if (result.error) return `❌ ${result.error}`;

    let msg = `*Scanner: ${result.scannerName}*\n`;
    msg += `Scanned: ${result.totalScanned} stocks\n`;
    msg += `Matched: ${result.totalMatched} stocks\n\n`;

    if (result.results?.length > 0) {
      msg += `*Matching Stocks:*\n`;
      result.results.slice(0, 10).forEach((r: any) => {
        const changeEmoji = r.pChange >= 0 ? '🟢' : '🔴';
        msg += `${changeEmoji} *${r.symbol}* — ₹${r.lastPrice?.toFixed(2)} (${r.pChange >= 0 ? '+' : ''}${r.pChange?.toFixed(2)}%)\n`;
        r.matchedConditions.forEach((c: string) => {
          msg += `   ✓ ${c}\n`;
        });
      });
    } else {
      msg += `No stocks matched this scanner's criteria today.`;
    }

    return msg;
  }

  getMessageLog(): any[] {
    return this.messageLog.slice(-50);
  }

  updateBotStatus(enabled: boolean): any {
    this.botEnabled = enabled;
    return { botEnabled: this.botEnabled };
  }

  simulateQrCode(): any {
    this.qrCodeData = `whatsapp-bot-qr-${Date.now()}`;
    return {
      qrCode: this.qrCodeData,
      message: 'In production, scan this QR code with WhatsApp to connect the bot',
      note: 'whatsapp-web.js requires a headless Chrome environment. For production deployment, ensure puppeteer is properly configured.',
    };
  }
}
