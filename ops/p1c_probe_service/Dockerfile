FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir requests

COPY p1c_probe_standalone.py ./p1c_probe_standalone.py

CMD ["python", "p1c_probe_standalone.py", "--start-date", "2022-11-20", "--end-date", "2022-12-18", "--timeout-seconds", "10"]
