FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install dependencies dulu (agar hasilnya di-cache oleh platform)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Salin sisa kode backend
COPY . .

EXPOSE 8000

# Jalankan migrasi DB, lalu start server.
# $PORT disediakan otomatis oleh Render/Railway/Fly.io.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
