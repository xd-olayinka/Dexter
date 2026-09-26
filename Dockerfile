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
COPY server/ .
COPY --from=web /web/dist /app/static
ENV DEXTER_HOST=0.0.0.0 DEXTER_STATIC_DIR=/app/static DEXTER_REQUIRE_AUTH=true DEXTER_SIGNUP_MODE=first
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
