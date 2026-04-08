import { Module } from '@nestjs/common';
import { ScannersController } from './scanners.controller';
import { ScannersService } from './scanners.service';
import { YahooService } from '../../common/yahoo/yahoo.service';
import { NseService } from '../../common/nse/nse.service';

@Module({
  controllers: [ScannersController],
  providers: [ScannersService, YahooService, NseService],
  exports: [ScannersService],
})
export class ScannersModule {}
