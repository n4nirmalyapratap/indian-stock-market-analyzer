import { Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiQuery } from '@nestjs/swagger';
import { PatternsService } from './patterns.service';

@ApiTags('Chart Patterns')
@Controller('patterns')
export class PatternsController {
  constructor(private readonly patternsService: PatternsService) {}

  @Get()
  @ApiOperation({ summary: 'Get detected chart patterns across Nifty 100, Midcap and Smallcap' })
  @ApiQuery({ name: 'universe', required: false, description: 'Filter: NIFTY100, MIDCAP, SMALLCAP' })
  @ApiQuery({ name: 'signal', required: false, description: 'Filter: CALL or PUT' })
  getPatterns(@Query('universe') universe?: string, @Query('signal') signal?: string) {
    return this.patternsService.getPatterns(universe, signal);
  }

  @Post('scan')
  @ApiOperation({ summary: 'Trigger a manual chart pattern scan' })
  triggerScan() {
    return this.patternsService.triggerScan();
  }
}
