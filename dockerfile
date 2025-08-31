# syntax=docker/dockerfile:1
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy source files
COPY main.py utils.py /app/

# Install deps
RUN pip install --no-cache-dir requests python-dotenv
RUN pip install --no-cache-dir requests python-dotenv yt-dlp
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
  && rm -rf /var/lib/apt/lists/*


# Default output directory inside container
ENV OUTPUT_DIR=/downloads

# Volume mount so you get files back on host
VOLUME ["/downloads"]

ENTRYPOINT ["python", "/app/main.py"]
