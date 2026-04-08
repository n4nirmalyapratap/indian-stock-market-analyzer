import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiParam, ApiQuery } from '@nestjs/swagger';
import { SectorsService } from './sectors.service';

@ApiTags('Sectors')
@Controller('sectors')
export class SectorsController {
  constructor(private readonly sectorsService: SectorsService) {}

  @Get()
  @ApiOperation({ summary: 'Get all NSE sector indices with performance data' })
  getAllSectors() {
    return this.sectorsService.getAllSectors();
  }

  @Get('rotation')
  @ApiOperation({ summary: 'Get sector rotation analysis - where is money flowing' })
  getSectorRotation() {
    return this.sectorsService.getSectorRotation();
  }

  @Get(':symbol')
  @ApiOperation({ summary: 'Get specific sector details' })
  @ApiParam({ name: 'symbol', description: 'Sector index symbol e.g. NIFTY BANK' })
  getSectorDetail(@Param('symbol') symbol: string) {
    return this.sectorsService.getSectorDetail(symbol);
  }
}
