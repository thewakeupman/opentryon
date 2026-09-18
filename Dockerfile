FROM python:3.12-slim AS web
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY licenses ./licenses
COPY app ./app
COPY scripts ./scripts
RUN pip install . && useradd --create-home --uid 10001 studio \
    && mkdir -p /app/data /app/weights && chown -R studio:studio /app
USER studio
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

FROM web AS gpu
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
# PyTorch wheels supply CUDA runtime libraries. Host needs NVIDIA driver + Container Toolkit.
RUN pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124 \
    && pip install '.[inference]'
USER studio
