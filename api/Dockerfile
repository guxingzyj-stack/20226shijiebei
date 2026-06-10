FROM python:3.12-slim

WORKDIR /app
COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
CMD ["sh", "-lc", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
