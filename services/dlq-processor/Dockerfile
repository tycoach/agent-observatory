FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY processor.py .

RUN useradd -m -u 1000 observatory && \
    chown -R observatory:observatory /app

USER observatory

CMD ["python", "-u", "processor.py"]