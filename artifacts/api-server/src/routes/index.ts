import { Router, type IRouter } from "express";
import healthRouter from "./health";
import sectorsRouter from "./sectors";
import stocksRouter from "./stocks";
import patternsRouter from "./patterns";
import scannersRouter from "./scanners";
import whatsappRouter from "./whatsapp";

const router: IRouter = Router();

router.use(healthRouter);
router.use("/sectors", sectorsRouter);
router.use("/stocks", stocksRouter);
router.use("/patterns", patternsRouter);
router.use("/scanners", scannersRouter);
router.use("/whatsapp", whatsappRouter);

export default router;
