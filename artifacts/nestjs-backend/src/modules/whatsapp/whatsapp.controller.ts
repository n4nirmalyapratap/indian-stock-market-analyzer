import { Controller, Get, Post, Body, Put, Param } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBody } from '@nestjs/swagger';
import { WhatsappService, BotMessage } from './whatsapp.service';

@ApiTags('WhatsApp Bot')
@Controller('whatsapp')
export class WhatsappController {
  constructor(private readonly whatsappService: WhatsappService) {}

  @Get('status')
  @ApiOperation({ summary: 'Get WhatsApp bot connection status' })
  getStatus() {
    return this.whatsappService.getBotStatus();
  }

  @Post('message')
  @ApiOperation({ summary: 'Process a message through the bot (webhook or test endpoint)' })
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        from: { type: 'string', example: '919876543210@c.us' },
        body: { type: 'string', example: 'RELIANCE' },
        timestamp: { type: 'string', example: '2024-01-01T10:00:00Z' },
      },
    },
  })
  processMessage(@Body() message: BotMessage) {
    return this.whatsappService.processMessage(message);
  }

  @Get('messages')
  @ApiOperation({ summary: 'Get recent message log' })
  getMessages() {
    return this.whatsappService.getMessageLog();
  }

  @Post('qr')
  @ApiOperation({ summary: 'Generate QR code for WhatsApp Web connection' })
  generateQr() {
    return this.whatsappService.simulateQrCode();
  }

  @Put('status')
  @ApiOperation({ summary: 'Enable or disable the bot' })
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        enabled: { type: 'boolean' },
      },
    },
  })
  updateStatus(@Body() body: { enabled: boolean }) {
    return this.whatsappService.updateBotStatus(body.enabled);
  }
}
