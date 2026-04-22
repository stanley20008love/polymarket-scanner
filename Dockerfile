FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN printf '[server]\nheadless = true\nenableCORS = false\nenableXsrfProtection = false\naddress = "0.0.0.0"\n\n[browser]\ngatherUsageStats = false\n' > .streamlit/config.toml

ENV PORT=8501
EXPOSE 8501

CMD ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--server.enableCORS=false", "--server.enableXsrfProtection=false", "--browser.gatherUsageStats=false"]
