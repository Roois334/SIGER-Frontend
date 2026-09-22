import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import Config
from utilities.decorators import login_required, admin_required

app = Flask(__name__)
app.config.from_object(Config)

BACKEND_URL = "http://127.0.0.1:5000"

MUNICIPIOS_SABANA_OCCIDENTE = [
    "Facatativa", "Madrid", "Mosquera", "Funza", "Bojaca",
    "El Rosal", "Subachoque", "Zipacon",
]

ROLE_LABELS = {
    "ciudadano": "Ciudadano",
    "gestor_municipal": "Gestor municipal",
    "organismo_atencion": "Organismo de atencion",
    "administrador": "Administrador",
}


def _auth_headers():
    """Cabecera con el JWT guardado en sesion, para llamar al backend protegido."""
    return {"Authorization": "Bearer " + session.get("token", "")}


@app.route("/")
def index():
    if "usuario" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        try:
            r = requests.post(BACKEND_URL + "/api/auth/login",
                               json={"email": email, "password": password}, timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return render_template("login.html")

        if r.status_code == 200:
            data = r.json()
            session["usuario"] = data["usuario"]
            session["token"] = data["token"]
            flash("Bienvenido, " + data["usuario"]["nombre"] + "!", "success")
            return redirect(url_for("dashboard"))

        flash(r.json().get("error", "Correo o contrasena incorrectos"), "error")

    return render_template("login.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if "usuario" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        payload = {
            "nombre": request.form.get("nombre", "").strip(),
            "apellido": request.form.get("apellido", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "municipio": request.form.get("municipio", "").strip(),
            "password": request.form.get("password", ""),
            "rol": "ciudadano",
        }
        confirmar = request.form.get("confirmar", "")

        if payload["password"] != confirmar:
            flash("Las contrasenas no coinciden", "error")
            return render_template("registro.html", municipios=MUNICIPIOS_SABANA_OCCIDENTE)

        try:
            r = requests.post(BACKEND_URL + "/api/auth/register", json=payload, timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return render_template("registro.html", municipios=MUNICIPIOS_SABANA_OCCIDENTE)

        if r.status_code == 201:
            data = r.json()
            session["usuario"] = data["usuario"]
            session["token"] = data["token"]
            flash("Cuenta creada. Bienvenido a SIGER, " + payload["nombre"] + "!", "success")
            return redirect(url_for("dashboard"))

        flash(r.json().get("error", "No se pudo crear la cuenta"), "error")

    return render_template("registro.html", municipios=MUNICIPIOS_SABANA_OCCIDENTE)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html",
                            role_label=ROLE_LABELS.get(session["usuario"]["rol"], session["usuario"]["rol"]))

@app.route("/admin/usuarios")
@admin_required
def admin_usuarios():
    filtros = {
        "q": request.args.get("q", "").strip(),
        "rol": request.args.get("rol", ""),
        "estado": request.args.get("estado", ""),
    }
    params = {k: v for k, v in filtros.items() if v}

    try:
        r = requests.get(BACKEND_URL + "/api/usuarios", headers=_auth_headers(), params=params, timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return render_template("admin_usuarios.html", usuarios=[], filtros=filtros, role_labels=ROLE_LABELS)

    if r.status_code != 200:
        flash(r.json().get("error", "No se pudo cargar la lista de usuarios"), "error")
        return render_template("admin_usuarios.html", usuarios=[], filtros=filtros, role_labels=ROLE_LABELS)

    usuarios = r.json().get("usuarios", [])
    return render_template("admin_usuarios.html", usuarios=usuarios, filtros=filtros, role_labels=ROLE_LABELS)


@app.route("/admin/usuarios/<int:user_id>/editar", methods=["GET", "POST"])
@admin_required
def admin_usuario_editar(user_id):
    if request.method == "POST":
        payload = {
            "nombre": request.form.get("nombre", "").strip(),
            "apellido": request.form.get("apellido", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "municipio": request.form.get("municipio", ""),
            "rol": request.form.get("rol", ""),
        }
        try:
            r = requests.put(BACKEND_URL + f"/api/usuarios/{user_id}",
                              json=payload, headers=_auth_headers(), timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return redirect(url_for("admin_usuario_editar", user_id=user_id))

        if r.status_code == 200:
            flash("Usuario actualizado correctamente", "success")
            return redirect(url_for("admin_usuarios"))

        flash(r.json().get("error", "No se pudo actualizar el usuario"), "error")
        return redirect(url_for("admin_usuario_editar", user_id=user_id))

    try:
        r = requests.get(BACKEND_URL + f"/api/usuarios/{user_id}", headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for("admin_usuarios"))

    if r.status_code != 200:
        flash(r.json().get("error", "Usuario no encontrado"), "error")
        return redirect(url_for("admin_usuarios"))

    usuario = r.json()["usuario"]
    return render_template("admin_usuario_editar.html",
                            usuario=usuario, role_labels=ROLE_LABELS,
                            municipios=MUNICIPIOS_SABANA_OCCIDENTE)


@app.route("/admin/usuarios/<int:user_id>/estado", methods=["POST"])
@admin_required
def admin_usuario_estado(user_id):
    nuevo_estado = request.form.get("activo") == "1"
    try:
        r = requests.patch(BACKEND_URL + f"/api/usuarios/{user_id}/estado",
                            json={"activo": nuevo_estado}, headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for("admin_usuarios"))

    if r.status_code == 200:
        flash("Cuenta activada correctamente" if nuevo_estado else "Cuenta desactivada correctamente", "success")
    else:
        flash(r.json().get("error", "No se pudo cambiar el estado del usuario"), "error")

    return redirect(url_for("admin_usuarios"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Sesion cerrada correctamente", "success")
    return redirect(url_for("login"))


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=5001)
