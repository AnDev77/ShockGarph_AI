FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SHOCKGRAPH_SERVICE_MODE=demo
COPY infra/requirements-runtime.txt /app/requirements-runtime.txt
RUN python -m pip install --no-cache-dir --require-hashes -r requirements-runtime.txt
COPY pyproject.toml /app/
COPY packages/event_study /app/packages/event_study
COPY apps/api /app/apps/api
RUN python -m pip install --no-cache-dir --no-deps . && useradd --create-home --uid 10001 shockgraph
USER shockgraph
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health/ready',timeout=3)"
CMD ["sh", "-c", "exec uvicorn shockgraph_api.app:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
