# Combined Dexter image (Railway): builds the frontend, then serves it and the API from one
# FastAPI process on $PORT. server/Dockerfile remains the API-only image for docker compose.
FROM node:22-slim AS web
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV VITE_API_URL=same-origin
RUN npx vite build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Anthony's browser (browse_url tool, JS-page ingest) — Chromium + its system libraries
RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium
# Piper voices for spoken briefings (Dexter + Anthony), downloaded at build so startup needs no network.
# Live mic voice (VAD/STT) needs torch and stays off in this image.
RUN pip install --no-cache-dir piper-tts==1.2.0  && python -c "from pathlib import Path; from piper.download import get_voices, ensure_voice_exists; d=Path.home()/'.local/share/piper_voices'; d.mkdir(parents=True, exist_ok=True); v=get_voices(str(d)); [ensure_voice_exists(n, [str(d)], str(d), v) for n in ('en_US-lessac-medium','en_GB-alan-medium')]"
COPY server/ .
COPY --from=web /web/dist /app/static
ENV DEXTER_HOST=0.0.0.0 DEXTER_STATIC_DIR=/app/static DEXTER_REQUIRE_AUTH=true DEXTER_SIGNUP_MODE=first
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
