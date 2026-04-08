import { Module } from '@nestjs/common';
import { SectorsController } from './sectors.controller';
import { SectorsService } from './sectors.service';
import { NseService } from '../../common/nse/nse.service';
import { YahooService } from '../../common/yahoo/yahoo.service';

@Module({
  controllers: [SectorsController],
  providers: [SectorsService, NseService, YahooService],
  exports: [SectorsService],
})
export class SectorsModule {}
