FROM python:3.12.9-slim-bookworm@sha256:48a11b7ba705fd53bf15248d1f94d36c39549903c5d59edcfa2f3f84126e7b44

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/mediaIntelligence/requirements.lock /app/requirements.lock
RUN python -m pip install --requirement /app/requirements.lock

COPY services/mediaIntelligence /app/services/mediaIntelligence
COPY packages/contracts/schemas /app/packages/contracts/schemas
RUN python -m pip install --no-deps --no-build-isolation /app/services/mediaIntelligence \
    && useradd --create-home --uid 10001 skilltwin \
    && chown -R skilltwin:skilltwin /app

USER skilltwin
WORKDIR /app/services/mediaIntelligence

CMD ["python", "-m", "mediaIntelligence.cli", "--help"]
