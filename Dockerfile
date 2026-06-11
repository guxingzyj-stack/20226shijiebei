FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=.

RUN pip install --no-cache-dir requests

COPY . .

CMD ["python", "-m", "model.p1c_probe", "--start-date", "2022-11-20", "--end-date", "2022-12-18", "--timeout-seconds", "10"]
