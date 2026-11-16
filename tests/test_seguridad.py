"""La contrasena del login viaja cifrada en los dos tramos: navegador->frontend y frontend->backend."""
import importlib
import re

import pytest
import requests as requests_real

import utilities.api as api
from utilities import seguridad

HTTP = {"X-Forwarded-Proto": "http"}
HTTPS = {"X-Forwarded-Proto": "https"}


class _Respuesta:
    def __init__(self, estado=200, cuerpo=None):
        self.status_code, self._cuerpo = estado, cuerpo or {}

    def json(self):
        return self._cuerpo

    def __bool__(self):
        return self.status_code < 400


def _csrf(client):
    html = client.get("/login", headers=HTTPS).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class TestUrls:
    @pytest.mark.parametrize("url,esperado", [
        ("http://127.0.0.1:5000", True), ("http://localhost:5000/", True), ("http://[::1]:5000", True),
        ("https://backend.azurewebsites.net", False), ("http://backend.azurewebsites.net", False), ("", False),
    ])
    def test_es_url_local(self, url, esperado):
        assert seguridad.es_url_local(url) is esperado

    def test_backend_remoto_por_http_se_corrige_a_https(self, caplog):
        assert seguridad.url_backend_segura("http://siger-backend.azurewebsites.net/") == "https://siger-backend.azurewebsites.net"
        assert "HTTP" in caplog.text

    def test_backend_local_o_https_no_se_toca(self):
        assert seguridad.url_backend_segura("http://127.0.0.1:5000/") == "http://127.0.0.1:5000"
        assert seguridad.url_backend_segura("https://x.com") == "https://x.com"

    def test_conexion_segura(self):
        assert seguridad.conexion_segura("https://x.com/a") and seguridad.conexion_segura("http://localhost:5000/a")
        assert not seguridad.conexion_segura("http://x.com/a")


class TestClienteHttp:
    def test_no_envia_nada_por_http_a_un_servidor_remoto(self, monkeypatch):
        monkeypatch.setattr(requests_real, "request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe salir")))
        with pytest.raises(requests_real.exceptions.ConnectionError, match="HTTPS"):
            api.requests.post("http://backend.remoto.com/api/auth/login", json={"password": "secreta"})

    def test_si_envia_por_https_y_marca_sesion_vencida(self, monkeypatch):
        monkeypatch.setattr(requests_real, "request", lambda *a, **k: _Respuesta(401))
        with pytest.raises(api.SesionExpirada):
            api.requests.get("https://b.com/x", headers={"Authorization": "Bearer abc"})


class TestFrontend:
    def test_pagina_de_login_por_http_redirige_a_https(self, client):
        r = client.get("/login", headers=HTTP)
        assert r.status_code == 301 and r.headers["Location"].startswith("https://")

    def test_el_envio_del_formulario_por_http_no_se_procesa(self, client, monkeypatch):
        import app as modulo
        monkeypatch.setattr(modulo.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe llamar al backend")))
        r = client.post("/login", headers=HTTP, data={"email": "a@b.com", "password": "Clave.1234"})
        assert r.status_code == 426

    def test_login_por_https_va_al_backend_https_y_no_se_guarda_en_cache(self, client, monkeypatch):
        import app as modulo
        enviados = []

        def falso(url, **kwargs):
            enviados.append((url, kwargs))
            return _Respuesta(200, {"token": "t", "usuario": {"nombre": "Ana", "rol": "ciudadano"}})

        monkeypatch.setattr(modulo.requests, "post", falso)
        r = client.post("/login", headers=HTTPS, data={"email": "A@b.com", "password": "Clave.1234", "csrf_token": _csrf(client)})
        assert r.status_code == 302
        url, kwargs = enviados[0]
        assert url == "https://backend.ejemplo.test/api/auth/login" and kwargs["json"]["password"] == "Clave.1234"
        pagina = client.get("/login", headers=HTTPS)
        assert "no-store" in pagina.headers["Cache-Control"] and "Strict-Transport-Security" in pagina.headers

    def test_la_contrasena_no_aparece_en_la_respuesta_ni_en_la_url(self, client, monkeypatch):
        import app as modulo
        monkeypatch.setattr(modulo.requests, "post", lambda *a, **k: _Respuesta(401, {"error": "Correo o contrasena incorrectos"}))
        r = client.post("/login", headers=HTTPS, data={"email": "a@b.com", "password": "Clave.1234", "csrf_token": _csrf(client)})
        assert "Clave.1234" not in r.get_data(as_text=True) and "Clave.1234" not in r.headers.get("Location", "")

    def test_el_formulario_envia_por_post_y_oculta_la_contrasena(self, client):
        html = client.get("/login", headers=HTTPS).get_data(as_text=True)
        assert '<form method="POST">' in html and 'type="password"' in html


class TestCookieDeSesion:
    def _config(self, monkeypatch, **entorno):
        import config
        for k in ("SESSION_COOKIE_SECURE", "BACKEND_URL"):
            monkeypatch.delenv(k, raising=False)
        for k, v in entorno.items():
            monkeypatch.setenv(k, v)
        return config._cookie_segura()

    def test_local_apagada_remoto_encendida(self, monkeypatch):
        assert self._config(monkeypatch) is False
        assert self._config(monkeypatch, BACKEND_URL="https://backend.azurewebsites.net") is True

    def test_la_variable_manda(self, monkeypatch):
        assert self._config(monkeypatch, BACKEND_URL="https://x.com", SESSION_COOKIE_SECURE="0") is False
        assert self._config(monkeypatch, SESSION_COOKIE_SECURE="1") is True

    def test_la_app_de_pruebas_usa_cookie_segura_y_httponly(self, app):
        assert app.config["SESSION_COOKIE_SECURE"] is True and app.config["SESSION_COOKIE_HTTPONLY"] is True
