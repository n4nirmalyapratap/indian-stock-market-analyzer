import express, { type Express } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
// ── CORS ────────────────────────────────────────────────────────────────────
// Pin to dev hosts plus optional comma-separated CORS_ALLOWED_ORIGINS from env.
// Mirrors the policy in the FastAPI backend (artifacts/python-backend/main.py).
// Setting CORS_ALLOWED_ORIGINS="*" is intentionally not honoured here.
// ────────────────────────────────────────────────────────────────────────────
const DEFAULT_DEV_ORIGINS = [
  "http://localhost:3002",
  "http://localhost:5000",
  "http://localhost:5173",
  "http://localhost:5174",
  "http://localhost:8080",
  "http://127.0.0.1:3002",
  "http://127.0.0.1:5000",
  "http://127.0.0.1:5173",
  "http://127.0.0.1:5174",
  "http://127.0.0.1:8080",
];
const extraOrigins = (process.env.CORS_ALLOWED_ORIGINS ?? "")
  .split(",")
  .map((o) => o.trim())
  .filter((o) => o.length > 0 && o !== "*");
const allowedOrigins = new Set([...DEFAULT_DEV_ORIGINS, ...extraOrigins]);

app.use(
  cors({
    origin(origin, cb) {
      // Allow requests with no Origin header (curl, server-to-server).
      if (!origin) return cb(null, true);
      if (allowedOrigins.has(origin)) return cb(null, true);
      // For disallowed origins, simply don't reflect the origin header so
      // the browser's same-origin-policy blocks the response. Returning an
      // Error here would surface as a 500 to clients, which is noisier
      // than necessary.
      cb(null, false);
    },
    credentials: false,
  }),
);
app.use(express.json({ limit: "1mb" }));
app.use(express.urlencoded({ extended: false, limit: "1mb" }));

app.use("/api", router);

export default app;
