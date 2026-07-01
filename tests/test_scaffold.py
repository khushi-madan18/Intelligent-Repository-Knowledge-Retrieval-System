import importlib


def test_src_reporag_import_acceptance_check() -> None:
    module = importlib.import_module("src.reporag")

    assert module.__version__ == "0.1.0"


def test_api_health_endpoint_shape() -> None:
    from src.reporag.api.main import health

    assert health() == {"status": "ok"}
