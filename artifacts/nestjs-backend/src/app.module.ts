import { Module } from '@nestjs/common';
import { ScheduleModule } from '@nestjs/schedule';
import { ConfigModule } from '@nestjs/config';
import { SectorsModule } from './modules/sectors/sectors.module';
import { StocksModule } from './modules/stocks/stocks.module';
import { PatternsModule } from './modules/patterns/patterns.module';
import { ScannersModule } from './modules/scanners/scanners.module';
import { WhatsappModule } from './modules/whatsapp/whatsapp.module';
import { HealthModule } from './modules/health/health.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    ScheduleModule.forRoot(),
    HealthModule,
    SectorsModule,
    StocksModule,
    PatternsModule,
    ScannersModule,
    WhatsappModule,
  ],
})
export class AppModule {}
