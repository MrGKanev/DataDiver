FROM python:3.12-slim

LABEL maintainer="Gabriel Kanev"
LABEL description="DataDiver - Modern async web scraper"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install httpx beautifulsoup4 lxml rich typer aiofiles

# Copy application
COPY datadiver.py .

# Create output directory
RUN mkdir -p /output

WORKDIR /output

ENTRYPOINT ["python", "/app/datadiver.py"]
CMD ["--help"]
