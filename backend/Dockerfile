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

# Copy dependencies
COPY . /app

# Install Python packages
RUN uv pip install --system fastapi "uvicorn[standard]" "pydantic>=2.7" pydantic-settings "sqlalchemy>=2.0" alembic pyjwt cryptography argon2-cffi python-multipart httpx pytest pytest-asyncio python-dotenv email-validator

# Ensure uploads directory
RUN mkdir -p /app/uploads/complaints /app/uploads/resolutions

EXPOSE 8000

CMD ["sh", "-c", "python bootstrap.py && python seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

