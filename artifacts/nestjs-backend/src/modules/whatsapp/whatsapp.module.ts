import { Module } from '@nestjs/common';
import { WhatsappController } from './whatsapp.controller';
import { WhatsappService } from './whatsapp.service';
import { SectorsModule } from '../sectors/sectors.module';
import { StocksModule } from '../stocks/stocks.module';
import { PatternsModule } from '../patterns/patterns.module';
import { ScannersModule } from '../scanners/scanners.module';

@Module({
  imports: [SectorsModule, StocksModule, PatternsModule, ScannersModule],
  controllers: [WhatsappController],
  providers: [WhatsappService],
})
export class WhatsappModule {}
