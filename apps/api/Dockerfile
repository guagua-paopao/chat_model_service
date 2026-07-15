FROM python:3.12.3-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN python -m pip install -r requirements.lock
COPY apps/api/src /app/apps/api/src
COPY alembic.ini /app/alembic.ini
COPY apps/api/migrations /app/apps/api/migrations

ENV PYTHONPATH=/app/apps/api/src
USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "qa_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
