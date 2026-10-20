# Hardcore Draft: one container serving the API and the built frontend from the same address.
#
#   docker build -t hardcore-draft .
#   docker run -p 8000:8000 -e DATABASE_URL=postgresql://... -e RIOT_API_KEY=... hardcore-draft
#
# Railway builds this automatically (railway.json) and sets PORT.

# --- 1. build the frontend --------------------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. the backend, serving the build ---------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/frontend/dist \
    LIVE_CLIENT_URL=off \
    PORT=8000
WORKDIR /app/backend

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
# Editable: the app runs from this folder, next to its migrations (alembic/).
RUN pip install -e .

COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Run as a normal user, not root.
RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
# --proxy-headers: Railway's proxy terminates HTTPS, so trust X-Forwarded-Proto for secure cookies.
# One worker on purpose: the background jobs (match poller, build crawler, live tracker) run in-process.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --workers 1"]
