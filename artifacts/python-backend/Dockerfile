FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────────
# gcc/g++ are required to compile C extensions in scipy and other packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies from PyPI ─────────────────────────────────────────────
# Copied before source so this layer is cached as long as requirements.txt
# does not change — even if source files change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── spaCy language model ───────────────────────────────────────────────────────
# Downloaded at build time so the container starts immediately.
# This is its own layer — cached unless the spacy version changes.
RUN python -m spacy download en_core_web_sm

# ── Application source ─────────────────────────────────────────────────────────
# Copied last so that source changes only invalidate this layer and nothing above.
# This includes the pandas_ta/ shim directory (a local package, not on PyPI).
COPY . .

# ── Python path ────────────────────────────────────────────────────────────────
# pandas_ta is a local folder shim inside /app/pandas_ta/.
# Setting PYTHONPATH=/app ensures Python finds it regardless of how uvicorn is
# invoked. This backs up the sys.path.insert already in run.py and indicators.py.
ENV PYTHONPATH=/app

ENV PORT=8090
EXPOSE 8090

CMD ["python", "run.py"]
