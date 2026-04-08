import { Router, Request, Response } from 'express';
import { YahooService } from '../services/yahoo.service';
import { NseService } from '../services/nse.service';
import { PatternsService } from '../services/patterns.service';

const router = Router();

let patternsService: PatternsService | null = null;

function getService() {
  if (!patternsService) {
    const yahoo = new YahooService();
    const nse = new NseService();
    patternsService = new PatternsService(yahoo, nse);
  }
  return patternsService;
}

router.get('/', async (req: Request, res: Response) => {
  try {
    const service = getService();
    const { universe, signal, category } = req.query;
    const data = await service.getPatterns(
      universe  as string | undefined,
      signal    as string | undefined,
      category  as string | undefined,
    );
    res.json(data);
  } catch (err: any) {
    req.log.error({ err }, 'Failed to get patterns');
    res.status(500).json({ error: 'Failed to fetch pattern data' });
  }
});

router.post('/scan', async (req: Request, res: Response) => {
  try {
    const service = getService();
    const data = await service.triggerScan();
    res.json(data);
  } catch (err: any) {
    req.log.error({ err }, 'Failed to run scan');
    res.status(500).json({ error: 'Failed to run pattern scan' });
  }
});

export default router;
