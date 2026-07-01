"""FastAPI application entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="Intelligent Repository Knowledge Retrieval System")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Return basic application health."""

    return {"status": "ok"}
