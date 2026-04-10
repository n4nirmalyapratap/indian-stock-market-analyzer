FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model at build time so the container starts immediately
RUN python -m spacy download en_core_web_sm

# Copy application source
COPY . .

EXPOSE 8090

ENV PORT=8090

CMD ["python", "run.py"]
