FROM python:3.12-slim

WORKDIR /app
COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY . /app
COPY data/script_predictions_groupstage.json /app/data/script_predictions_groupstage.json
COPY scripts/import_script_predictions.py /app/scripts/import_script_predictions.py

ENV PYTHONUNBUFFERED=1
CMD ["sh", "-lc", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
