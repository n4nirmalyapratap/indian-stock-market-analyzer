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
from app.routes.nlp import router as nlp_router
from app.routes.analytics import router as analytics_router

app = FastAPI(
    title="Indian Stock Market Analyzer — Python Backend",
    description=(
        "FastAPI backend for NSE sector rotation, stock analysis, chart patterns, "
        "custom scanners, NLP natural-language queries, and deep analytics."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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


app.include_router(health_router,    prefix="/api")
app.include_router(sectors_router,   prefix="/api")
app.include_router(stocks_router,    prefix="/api")
app.include_router(patterns_router,  prefix="/api")
app.include_router(scanners_router,  prefix="/api")
app.include_router(whatsapp_router,  prefix="/api")
app.include_router(nlp_router,       prefix="/api")
app.include_router(analytics_router, prefix="/api")
