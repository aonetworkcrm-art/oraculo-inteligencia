# ══════════════════════════════════════════════════════════════
#  Dockerfile — Oráculo de Inteligencia
#  Use for: Fly.io, Oracle Cloud VM, Railway (legacy), Koyeb, or any Docker host
# ══════════════════════════════════════════════════════════════
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (psutil, beautifulsoup need C libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Render/Fly.io will override with $PORT)
EXPOSE 8080

# Health check (port 8080 = default, $PORT overrides at runtime)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; p=os.environ.get('PORT','8080'); urllib.request.urlopen(f'http://localhost:{p}/api/stats')"

# Start with gunicorn
CMD gunicorn api:app --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 --keep-alive 5 --access-logfile -
