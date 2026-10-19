FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 18757 --no-create-home app
COPY server ./server
COPY web ./web
USER 18757:18757
ENV GABBAPROC_DB=/data/procs.sqlite3 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8757
CMD ["uvicorn","server.app:app","--host","0.0.0.0","--port","8757","--proxy-headers","--forwarded-allow-ips","172.30.87.1","--no-access-log","--limit-concurrency","64","--timeout-keep-alive","5"]
