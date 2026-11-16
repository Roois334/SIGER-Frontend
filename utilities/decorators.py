from functools import wraps
from flask import session, redirect, url_for, flash
from utilities.permisos import puede


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "usuario" not in session:
            flash("Debes iniciar sesion primero", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "usuario" not in session:
            flash("Debes iniciar sesion primero", "error")
            return redirect(url_for("login"))
        if session["usuario"].get("rol") != "administrador":
            flash("No tienes permisos para acceder a esa seccion", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def permiso_required(permiso):
    def decorador(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "usuario" not in session:
                flash("Debes iniciar sesion primero", "error")
                return redirect(url_for("login"))
            if not puede(session["usuario"], permiso):
                flash("No tienes permisos para acceder a esa seccion", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorador
