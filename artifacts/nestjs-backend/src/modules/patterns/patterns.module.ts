import { Module } from '@nestjs/common';
import { PatternsController } from './patterns.controller';
import { PatternsService } from './patterns.service';
import { NseService } from '../../common/nse/nse.service';
import { YahooService } from '../../common/yahoo/yahoo.service';

@Module({
  controllers: [PatternsController],
  providers: [PatternsService, NseService, YahooService],
  exports: [PatternsService],
})
export class PatternsModule {}
