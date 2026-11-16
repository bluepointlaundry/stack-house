# Stack House — production image (used by Railway; works on any Docker host).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    STACKHOUSE_HOST=0.0.0.0 \
    STACKHOUSE_DATA=/data \
    STACKHOUSE_TRUST_PROXY=1 \
    STACKHOUSE_SECURE_COOKIES=1 \
    STACKHOUSE_FORCE_HTTPS=1 \
    STACKHOUSE_VAPID_SUBJECT=https://stackhouse.alsalemkuwait.com

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY run.py .
COPY app ./app

# /data must be a persistent volume: it holds the database, photos and keys.
EXPOSE 8080
CMD ["python", "run.py"]
