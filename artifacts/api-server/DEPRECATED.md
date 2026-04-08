# DEPRECATED — API Server (Node.js)

This directory contains a Node.js/TypeScript API server that was part of an
earlier architecture of the Indian Stock Market Analyzer.

## Status: DEPRECATED — DO NOT USE

All API functionality is now served by the **Python FastAPI backend** at
`artifacts/python-backend/` on port 8090.

## What replaced it

The Python backend provides every endpoint this server once exposed, plus new
capabilities (NLP queries, analytics, WhatsApp NLP routing).

See `artifacts/python-backend/` for the current implementation.

## This code will not be updated

No bug fixes, feature additions, or dependency upgrades will be made here.
The workflow for this server has been removed from the project.
