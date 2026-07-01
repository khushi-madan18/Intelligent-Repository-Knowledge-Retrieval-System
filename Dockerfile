FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY tests ./tests
COPY examples ./examples
COPY scripts ./scripts
COPY .pre-commit-config.yaml ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "src.reporag.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
