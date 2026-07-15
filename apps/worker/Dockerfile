FROM python:3.12.3-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY apps/worker/src /app/src
USER 65532:65532
CMD ["python", "-m", "qa_worker.main"]
