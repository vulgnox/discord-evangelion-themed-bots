FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# If using SQLite (no DATABASE_URL), store data on a mounted volume
ENV SQLITE_PATH=/data/eva_bots.db

CMD ["python", "run_all_bots.py"]
