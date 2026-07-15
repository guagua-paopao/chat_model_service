FROM python:3.12.3-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/apps/api/src:/app/apps/worker/src
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN python -m pip install -r requirements.lock
COPY apps/api/src /app/apps/api/src
COPY apps/worker/src /app/apps/worker/src
USER 65532:65532
CMD ["python", "-m", "qa_worker.main"]
