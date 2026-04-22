FROM python:3.11-slim

WORKDIR /app

# Install system deps needed for scipy/numpy
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Streamlit config
RUN mkdir -p .streamlit && \
    printf '[server]\nheadless = true\nenableCORS = false\nenableXsrfProtection = false\naddress = "0.0.0.0"\n\n[browser]\ngatherUsageStats = false\n' > .streamlit/config.toml

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default PORT=8501, Zeabur overrides this
ENV PORT=8501

CMD streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false --browser.gatherUsageStats=false
