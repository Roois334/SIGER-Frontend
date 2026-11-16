import os

os.environ["SECRET_KEY"] = "clave-solo-para-pruebas-0123456789abcdef"
os.environ["BACKEND_URL"] = "https://backend.ejemplo.test"
os.environ.pop("SESSION_COOKIE_SECURE", None)
os.environ.pop("FORCE_HTTPS", None)

import pytest


@pytest.fixture(scope="session")
def app():
    import app as modulo
    modulo.app.config.update(TESTING=True)
    return modulo.app


@pytest.fixture
def client(app):
    return app.test_client()
