FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy both generator scripts
COPY event_generator.py .
COPY generator.py .

# Create non-root user
RUN useradd -m -u 1000 generator && \
    chown -R generator:generator /app

USER generator

# Default command 
CMD ["python", "-u", "generator.py"]