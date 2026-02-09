# StudyCompanion MCP Server - Personal Cybersecurity Study Assistant
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY studycompanion_server.py .

RUN mkdir -p /app/data/chromadb /app/data/sqlite /app/data/exports

RUN useradd -m -u 1000 mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser
CMD ["python", "studycompanion_server.py"]
