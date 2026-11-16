"""
Seguridad del transporte (HTTPS) del FRONTEND.

La contrasena viaja en dos tramos y los dos deben ir cifrados:
  1) navegador  -> este frontend   (lo exige aplicar_seguridad: rechaza el trafico HTTP)
  2) frontend   -> backend         (lo exige url_backend_segura / utilities/api.py: solo HTTPS, salvo en local)

Detras de Azure el proxy avisa con X-Forwarded-Proto si el cliente uso HTTP. En local (sin proxy)
no se bloquea nada. FORCE_HTTPS=0 en el entorno desactiva el rechazo (solo para depuracion).
"""
import logging
import os
from urllib.parse import urlparse

from flask import request, redirect

log = logging.getLogger("siger.seguridad")

HSTS = "max-age=31536000; includeSubDomains"
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


def es_host_local(host):
    """True para localhost / 127.0.0.1 / ::1 (con o sin puerto)."""
    host = (host or "").strip().lower()
    if host.startswith("["):
        host = host[1:].split("]")[0]
    elif host.count(":") == 1:
        host = host.split(":")[0]
    return host in HOSTS_LOCALES


def es_url_local(url):
    return es_host_local(urlparse(url or "").hostname)


def url_https(url):
    """Convierte http://... en https://... (si ya es https, la deja igual)."""
    return "https://" + url[len("http://"):] if url.lower().startswith("http://") else url


def url_backend_segura(url):
    """
    Devuelve la direccion del backend lista para usar (sin '/' final).
    Si apunta a un servidor remoto por HTTP, se corrige a HTTPS (y se avisa en el log):
    la contrasena del login nunca debe salir en claro hacia otro servidor.
    """
    url = (url or "").strip().rstrip("/")
    if url.lower().startswith("http://") and not es_url_local(url):
        segura = url_https(url)
        log.warning("BACKEND_URL usaba HTTP hacia un servidor remoto; se usara %s", segura)
        return segura
    return url


def conexion_segura(url):
    """True si es seguro mandar datos a esa URL: HTTPS, o HTTP solo hacia la propia maquina."""
    return url.lower().startswith("https://") or es_url_local(url)


def protocolo_cliente(req):
    cabecera = (req.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return cabecera or req.scheme


def llego_por_http(req):
    """True solo si el proxy dice de forma explicita que el cliente uso HTTP."""
    return (req.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower() == "http"


def aplicar_seguridad(app, rutas_sensibles=()):
    """Rechaza HTTP, envia HSTS y cabeceras basicas, y marca 'no-store' las rutas sensibles."""
    sensibles = tuple(rutas_sensibles)

    @app.before_request
    def exigir_https():
        if os.environ.get("FORCE_HTTPS", "1") == "0" or not llego_por_http(request):
            return None
        if request.method in ("GET", "HEAD"):
            return redirect(url_https(request.url), code=301)
        # Un POST (con la contrasena) NO se procesa: ya viajo sin cifrar
        return "Esta direccion solo acepta conexiones seguras (HTTPS)", 426

    @app.after_request
    def cabeceras_seguridad(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if protocolo_cliente(request) == "https":
            resp.headers.setdefault("Strict-Transport-Security", HSTS)
        if sensibles and request.path.startswith(sensibles):
            resp.headers["Cache-Control"] = "no-store"
            resp.headers.setdefault("Pragma", "no-cache")
        return resp

    return app
