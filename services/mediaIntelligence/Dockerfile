FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FFMPEG_PATH=/usr/bin/ffmpeg \
    FFPROBE_PATH=/usr/bin/ffprobe

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY mediaIntelligence ./mediaIntelligence

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && python -c "import boto3, cv2, jsonschema, PIL; import mediaIntelligence.pipeline"

ENTRYPOINT ["python", "-m", "mediaIntelligence.production"]
