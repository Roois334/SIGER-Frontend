import os
import secrets

from utilities.seguridad import es_url_local

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _cookie_segura():
    valor = os.environ.get("SESSION_COOKIE_SECURE")
    if valor is not None:
        return valor == "1"
    return not es_url_local(os.environ.get("BACKEND_URL", "http://127.0.0.1:5000"))


def _clave_secreta():
    clave = os.environ.get("SECRET_KEY")
    if clave:
        return clave
    carpeta = os.path.join(BASE_DIR, "instance")
    ruta = os.path.join(carpeta, "secret_key.txt")
    try:
        with open(ruta, encoding="utf-8") as f:
            clave = f.read().strip()
        if clave:
            return clave
    except OSError:
        pass
    clave = secrets.token_hex(32)
    try:
        os.makedirs(carpeta, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(clave)
    except OSError:
        pass
    return clave


class Config:
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    SECRET_KEY = _clave_secreta()

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _cookie_segura()

    MAX_CONTENT_LENGTH = 56 * 1024 * 1024
