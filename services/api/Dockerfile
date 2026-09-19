FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Migrations run as a separate step (`alembic upgrade head`) — never on container start,
# so several replicas booting at once cannot race each other through Alembic.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "--bind", "0.0.0.0:8000", "--timeout", "60", "app.main:app"]
