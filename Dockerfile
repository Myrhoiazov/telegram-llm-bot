FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY --chown=appuser:appuser skills ./skills
COPY --chown=appuser:appuser dashboard ./dashboard

RUN mkdir -p /app/data /app/workspace \
    && ln -s /app/skills /app/workspace/skills \
    && chown -R appuser:appuser /app/data /app/workspace

USER appuser

CMD ["python", "-m", "app.main"]
