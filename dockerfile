# syntax=docker/dockerfile:1
FROM python:3.12-slim

# System deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Python defaults + output dir
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OUTPUT_DIR=/downloads

WORKDIR /app

# Install Python deps)
RUN pip install --no-cache-dir requests python-dotenv yt-dlp

# Copy app code + entrypoint
COPY main.py utils.py /app/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Persist downloads on the host when mounted
VOLUME ["/downloads"]

ENTRYPOINT ["/entrypoint.sh"]
