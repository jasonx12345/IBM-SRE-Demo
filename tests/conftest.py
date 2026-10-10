import pytest

from api.app import create_app
from api.settings import load_config
from ingest.synthetic import SyntheticSource
from tests.fakes import MemoryRepository


@pytest.fixture
def config():
    config = load_config()
    config["model"]["cache_seconds"] = 0
    return config


@pytest.fixture
def source():
    return SyntheticSource()


@pytest.fixture
def repository(source):
    return MemoryRepository(source)


@pytest.fixture
def app(repository, config):
    app = create_app(repository, config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()
