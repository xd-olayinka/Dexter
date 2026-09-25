# Dexter backend — hostable anywhere that runs a container (Fly.io, Railway, Render, a VPS).
# Voice (torch/whisper/piper) and Playwright stay optional, as in requirements.txt; the image
# serves chat, Anthony, the ledger, projects, briefing, files and the Archive.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bind to all interfaces inside the container; the platform maps the port.
ENV DEXTER_HOST=0.0.0.0 DEXTER_PORT=8000
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
