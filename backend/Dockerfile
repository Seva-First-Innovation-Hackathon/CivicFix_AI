FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy application & dependency manifest
COPY . /app

# Install pinned Python packages (matches requirements.txt including Pillow, slowapi, google-genai, aiosmtplib)
RUN uv pip install --system -r /app/requirements.txt

# Ensure uploads directory
RUN mkdir -p /app/uploads/complaints /app/uploads/resolutions /app/uploads/evidence

EXPOSE 8000

CMD ["sh", "-c", "python migrate.py && ( [ -n \"$INITIAL_ADMIN_PASSWORD\" ] && python bootstrap.py || true ) && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
