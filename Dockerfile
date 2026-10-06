# Slim, single-stage image for Cloud Run (scale to zero). Build for arm64 too if you run on Axion/T2A.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/srv
WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY joulethief ./joulethief
COPY app ./app
COPY data ./data
COPY docs/results ./docs/results
USER 65532
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
