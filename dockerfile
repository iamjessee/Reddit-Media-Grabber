# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install system deps (ffmpeg for GIF/mp4 handling)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # default inside-container download dir
    OUTPUT_DIR=/downloads

WORKDIR /app

# Copy and install Python deps first for better layer caching
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Copy the app
COPY main.py utils.py /app/
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# Create a mount point for downloads
VOLUME ["/downloads"]

# Default entrypoint — accepts URL/ID args or prompts interactively
ENTRYPOINT ["/app/entrypoint.sh"]