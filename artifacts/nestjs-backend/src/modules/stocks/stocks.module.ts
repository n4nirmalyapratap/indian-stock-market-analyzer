import { Module } from '@nestjs/common';
import { StocksController } from './stocks.controller';
import { StocksService } from './stocks.service';
import { NseService } from '../../common/nse/nse.service';
import { YahooService } from '../../common/yahoo/yahoo.service';

@Module({
  controllers: [StocksController],
  providers: [StocksService, NseService, YahooService],
  exports: [StocksService],
})
export class StocksModule {}
