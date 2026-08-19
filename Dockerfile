FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER appuser

CMD ["python", "-m", "app.main"]
