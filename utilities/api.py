"""
Cliente HTTP unico para hablar con el backend.
- Si el backend responde 401/422 a una llamada que llevaba token, la sesion expiro:
  se lanza SesionExpirada y la app redirige al login (ver app.py).
- Los timeouts y otros fallos de red se tratan como ConnectionError (mensaje amable).
- response.json() nunca falla: si la respuesta no es JSON (ej. un 413 en HTML) devuelve {}.
"""
import requests as _requests


class SesionExpirada(Exception):
    pass


class _Respuesta:
    def __init__(self, r):
        self._r = r

    def __getattr__(self, nombre):
        return getattr(self._r, nombre)

    def __bool__(self):
        return bool(self._r)

    def json(self, *args, **kwargs):
        try:
            return self._r.json(*args, **kwargs)
        except ValueError:
            return {}


class _Api:
    exceptions = _requests.exceptions

    def request(self, metodo, url, **kwargs):
        # La base de datos remota (Filess) puede ser lenta: se espera al menos 15 segundos
        kwargs["timeout"] = max(kwargs.get("timeout") or 0, 15)
        try:
            r = _requests.request(metodo, url, **kwargs)
        except _requests.exceptions.ConnectionError:
            raise
        except _requests.exceptions.RequestException as e:
            raise _requests.exceptions.ConnectionError(str(e)) from e

        auth = ((kwargs.get("headers") or {}).get("Authorization") or "").strip()
        if r.status_code in (401, 422) and auth not in ("", "Bearer"):
            raise SesionExpirada()
        return _Respuesta(r)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def patch(self, url, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)


requests = _Api()
