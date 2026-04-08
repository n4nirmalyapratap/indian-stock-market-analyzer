import { Router, Request, Response } from 'express';
import { NseService } from '../services/nse.service';
import { YahooService } from '../services/yahoo.service';
import { SectorsService } from '../services/sectors.service';

const router = Router();

let sectorsService: SectorsService | null = null;

function getService() {
  if (!sectorsService) {
    const nse = new NseService();
    const yahoo = new YahooService();
    sectorsService = new SectorsService(nse, yahoo);
  }
  return sectorsService;
}

router.get('/', async (req: Request, res: Response) => {
  try {
    const service = getService();
    const data = await service.getAllSectors();
    res.json(data);
  } catch (err: any) {
    req.log.error({ err }, 'Failed to get sectors');
    res.status(500).json({ error: 'Failed to fetch sector data' });
  }
});

router.get('/rotation', async (req: Request, res: Response) => {
  try {
    const service = getService();
    const data = await service.getSectorRotation();
    res.json(data);
  } catch (err: any) {
    req.log.error({ err }, 'Failed to get rotation');
    res.status(500).json({ error: 'Failed to fetch rotation data' });
  }
});

router.get('/:symbol', async (req: Request, res: Response) => {
  try {
    const service = getService();
    const data = await service.getSectorDetail(String(req.params.symbol ?? ""));
    if (!data) {
      res.status(404).json({ error: 'Sector not found' });
      return;
    }
    res.json(data);
  } catch (err: any) {
    req.log.error({ err }, 'Failed to get sector detail');
    res.status(500).json({ error: 'Failed to fetch sector detail' });
  }
});

export default router;
