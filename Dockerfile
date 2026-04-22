FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8501
EXPOSE 8501

# First try: simple health check server on port 8501
# This tests if the basic container networking works
CMD python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.write = self.wfile.write
        self.write(b'<h1>Polymarket Scanner</h1><p>Service is running!</p>')
port = int(os.environ.get('PORT', 8501))
HTTPServer(('0.0.0.0', port), Handler).serve_forever()
"
