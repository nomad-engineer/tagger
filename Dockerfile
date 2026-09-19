# ---- Frontend build ----
FROM node:22-slim AS frontend
WORKDIR /frontend
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

# ---- Runtime ----
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    XDG_CONFIG_HOME=/tmp/config \
    XDG_CACHE_HOME=/tmp/cache \
    HF_HOME=/tmp/hf \
    TAGGER_LIBRARIES_ROOT=/library

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
