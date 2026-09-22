from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(view):
    """Exige que haya una sesion iniciada; si no, redirige al login."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "usuario" not in session:
            flash("Debes iniciar sesion primero", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """Exige sesion iniciada Y rol 'administrador'; si no, redirige al panel."""
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