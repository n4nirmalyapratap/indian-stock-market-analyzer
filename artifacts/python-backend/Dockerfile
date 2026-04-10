FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from PyPI
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the local pandas_ta shim as a proper pip package.
# This avoids any PYTHONPATH / sys.path issues at runtime.
COPY pandas_ta/ ./pandas_ta/
RUN pip install --no-cache-dir -e ./pandas_ta/

# Download spaCy model at build time so the container starts immediately
RUN python -m spacy download en_core_web_sm

# Copy the rest of the application source
COPY . .

EXPOSE 8090

ENV PORT=8090

CMD ["python", "run.py"]
