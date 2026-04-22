FROM python:3.12-slim

WORKDIR /app

# Install system dependencies and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install Python dependencies with pre-built wheels where possible
RUN pip install --no-cache-dir --extra-index-url https://pypi.org/simple/ \
    numpy>=2.0 \
    scipy>=1.14 \
    pandas>=2.2 \
    && pip install --no-cache-dir \
    web3>=6.0 \
    eth-account>=0.11 \
    plotly>=6.0 \
    streamlit>=1.35 \
    websocket-client>=1.7 \
    requests>=2.31 \
    aiohttp>=3.9 \
    pyyaml>=6.0 \
    python-dotenv>=1.0

# Copy all source files
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit dashboard
CMD ["streamlit", "run", "dashboard.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false", \
     "--server.maxUploadSize=50"]
