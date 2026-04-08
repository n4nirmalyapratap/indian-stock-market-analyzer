import { Controller, Get, Post, Put, Delete, Param, Body } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiParam, ApiBody } from '@nestjs/swagger';
import { ScannersService, ScannerConfig } from './scanners.service';

@ApiTags('Scanners')
@Controller('scanners')
export class ScannersController {
  constructor(private readonly scannersService: ScannersService) {}

  @Get()
  @ApiOperation({ summary: 'Get all saved scanners' })
  getAllScanners() {
    return this.scannersService.getAllScanners();
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get scanner by ID' })
  @ApiParam({ name: 'id', description: 'Scanner ID' })
  getScannerById(@Param('id') id: string) {
    const scanner = this.scannersService.getScannerById(id);
    if (!scanner) return { error: 'Scanner not found' };
    return scanner;
  }

  @Post()
  @ApiOperation({ summary: 'Create a new custom scanner' })
  createScanner(@Body() body: any) {
    return this.scannersService.createScanner(body);
  }

  @Put(':id')
  @ApiOperation({ summary: 'Update an existing scanner' })
  @ApiParam({ name: 'id', description: 'Scanner ID' })
  updateScanner(@Param('id') id: string, @Body() body: any) {
    const updated = this.scannersService.updateScanner(id, body);
    if (!updated) return { error: 'Scanner not found' };
    return updated;
  }

  @Delete(':id')
  @ApiOperation({ summary: 'Delete a scanner' })
  @ApiParam({ name: 'id', description: 'Scanner ID' })
  deleteScanner(@Param('id') id: string) {
    const deleted = this.scannersService.deleteScanner(id);
    return { success: deleted };
  }

  @Post(':id/run')
  @ApiOperation({ summary: 'Run a scanner and get matching stocks' })
  @ApiParam({ name: 'id', description: 'Scanner ID' })
  runScanner(@Param('id') id: string) {
    return this.scannersService.runScanner(id);
  }
}
