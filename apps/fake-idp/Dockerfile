FROM python:3.12.3-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN python -m pip install -r requirements.lock
COPY apps/fake-idp/src /app/src
USER 65532:65532
EXPOSE 9000
CMD ["uvicorn", "fake_idp.main:app", "--host", "0.0.0.0", "--port", "9000", "--no-access-log"]
