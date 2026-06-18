FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p crawler \
    && cp odds_crawler_once.py crawler/odds_crawler_once.py \
    && touch crawler/__init__.py

CMD ["python", "main.py"]
