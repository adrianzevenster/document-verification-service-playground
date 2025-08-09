FROM python:3.11-slim

RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
    build-essential gcc libgl1 libglib2.0-0 \
    poppler-utils libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash appuser
USER appuser
WORKDIR /app

COPY ../../requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

ENV PYTHONUNBUFFERED=1 \
    GOOGLE_APPLICATION_CREDENTIALS="/workspace/keys/sa.json" \
    CH_HOST="clickhouse" \
    CH_PORT="9000" \
    TUNED_GEMINI_MODEL="gemini-2.0-flash-lite"

CMD ["python", "-m", "processor.py"]