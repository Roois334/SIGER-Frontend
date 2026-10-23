import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _clave_secreta():
    """
    Usa SECRET_KEY del entorno. Si no existe, crea una clave al azar y la guarda en
    instance/secret_key.txt (esa carpeta no se sube a git). Nunca hay una clave fija en el codigo.
    """
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
        pass  # si no se puede guardar, la clave solo vale mientras corra el servidor
    return clave


class Config:
    # Modo depuracion: solo si defines FLASK_DEBUG=1 en el entorno
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    SECRET_KEY = _clave_secreta()

    # Cookie de sesion: no accesible desde JavaScript y no se envia desde otros sitios
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"  # ponlo en 1 con HTTPS

    # 5 evidencias x 10 MB + margen del formulario (igual que el backend)
    MAX_CONTENT_LENGTH = 56 * 1024 * 1024
