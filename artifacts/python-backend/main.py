import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.routes.health import router as health_router
from app.routes.sectors import router as sectors_router
from app.routes.stocks import router as stocks_router
from app.routes.patterns import router as patterns_router
from app.routes.scanners import router as scanners_router
from app.routes.whatsapp import router as whatsapp_router

app = FastAPI(
    title="Indian Stock Market Analyzer — Python Backend",
    description="FastAPI backend for NSE sector rotation, stock analysis, chart patterns, and custom scanners.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


api = FastAPI()
api.include_router(health_router)
api.include_router(sectors_router)
api.include_router(stocks_router)
api.include_router(patterns_router)
api.include_router(scanners_router)
api.include_router(whatsapp_router)

app.mount("/api", api)
