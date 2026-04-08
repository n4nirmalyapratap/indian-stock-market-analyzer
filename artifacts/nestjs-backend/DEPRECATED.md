# DEPRECATED — NestJS Backend

This directory contains the original NestJS/Node.js backend that was used during
the initial phase of the Indian Stock Market Analyzer project.

## Status: DEPRECATED — DO NOT USE

All backend functionality has been fully migrated to the **Python FastAPI backend**
located at `artifacts/python-backend/`.

## Why it was kept

This code is retained **for historical reference only** so that the migration
from Node.js to Python can be reviewed. It is not started by any workflow,
not referenced by the frontend, and will not receive any future updates.

## What replaced it

| Feature                  | Old (here)                         | New (use this)                         |
|--------------------------|------------------------------------|----------------------------------------|
| HTTP server              | NestJS (Node.js)                   | FastAPI (Python 3.11)                  |
| Stock data               | `src/sectors/`, `src/stocks/`      | `artifacts/python-backend/app/services/` |
| Pattern detection        | `src/patterns/`                    | `artifacts/python-backend/app/services/patterns_service.py` |
| Custom scanners          | `src/scanners/`                    | `artifacts/python-backend/app/services/scanners_service.py` |
| WhatsApp bot             | `src/whatsapp/`                    | `artifacts/python-backend/app/services/whatsapp_service.py` |
| NLP queries              | *(not present)*                    | `artifacts/python-backend/app/services/nlp_service.py` |
| Analytics                | *(not present)*                    | `artifacts/python-backend/app/services/analytics_service.py` |
| Port                     | 3001                               | 8090                                   |

## Do not start this server

The NestJS Backend workflow has been removed from the Replit project.
Starting this server manually will not affect the frontend — the frontend
Vite proxy routes all `/api` calls exclusively to the Python backend on port 8090.
