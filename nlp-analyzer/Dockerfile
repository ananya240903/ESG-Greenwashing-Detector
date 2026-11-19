FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# CPU-only torch keeps the image ~1.5 GB smaller than the default CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY esg ./esg
COPY scripts ./scripts
COPY tests ./tests
COPY pytest.ini report_generator.py ./

# docker-compose picks the worker: python -m esg.workers.parser_worker | analyzer_worker
CMD ["python", "-m", "esg.workers.parser_worker"]
