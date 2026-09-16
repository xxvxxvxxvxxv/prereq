FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PREREQ_CACHE=/data/catalog.sqlite3
WORKDIR /app
COPY requirements-production.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /data && chown app:app /data
COPY gunicorn.conf.py ./
COPY prereq ./prereq
COPY web ./web
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"
CMD ["gunicorn", "--config", "gunicorn.conf.py", "prereq.app:application"]
