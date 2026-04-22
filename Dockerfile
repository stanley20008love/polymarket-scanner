FROM python:3.11-slim
WORKDIR /app
RUN echo '<h1>Polymarket Scanner - Hello!</h1>' > index.html
EXPOSE 8501
ENV PORT=8501
CMD python -m http.server $PORT --bind 0.0.0.0
