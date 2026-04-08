import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiParam, ApiQuery } from '@nestjs/swagger';
import { StocksService } from './stocks.service';

@ApiTags('Stocks')
@Controller('stocks')
export class StocksController {
  constructor(private readonly stocksService: StocksService) {}

  @Get('nifty100')
  @ApiOperation({ summary: 'Get all Nifty 100 stocks with latest prices' })
  getNifty100() {
    return this.stocksService.getNifty100Stocks();
  }

  @Get('midcap')
  @ApiOperation({ summary: 'Get Nifty Midcap 150 stocks' })
  getMidcap() {
    return this.stocksService.getMidcapStocks();
  }

  @Get('smallcap')
  @ApiOperation({ summary: 'Get Nifty Smallcap 250 stocks' })
  getSmallcap() {
    return this.stocksService.getSmallcapStocks();
  }

  @Get(':symbol')
  @ApiOperation({ summary: 'Get detailed analysis for a specific stock' })
  @ApiParam({ name: 'symbol', description: 'NSE stock symbol e.g. RELIANCE, TCS, INFY' })
  getStockDetails(@Param('symbol') symbol: string) {
    return this.stocksService.getStockDetails(symbol);
  }
}
