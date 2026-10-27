FROM python:3.12-slim

ARG INSTALL_ML=false
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AUDIOEVAL_DATA_DIR=/data/jobs \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# ffmpeg adds M4A/AAC/WMA/WebM/AMR decoding; libsndfile ships inside the soundfile wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_ML" = "true" ]; then \
         pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu \
         && pip install --no-cache-dir -r requirements-ml.txt; \
       fi

COPY audioeval ./audioeval
RUN useradd --create-home --uid 10001 app && mkdir -p /data/jobs /models && chown -R app /data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["python", "-m", "uvicorn", "audioeval.web:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
