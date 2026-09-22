import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

BACKEND_URL = "http://127.0.0.1:5000"

MUNICIPIOS_SABANA_OCCIDENTE = [
    "Facatativa", "Madrid", "Mosquera", "Funza", "Bojaca",
    "El Rosal", "Subachoque", "Zipacon",
]


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
def dashboard():
    if "usuario" not in session:
        flash("Debes iniciar sesion primero", "error")
        return redirect(url_for("login"))

    ROLE_LABELS = {
        "ciudadano": "Ciudadano",
        "gestor_municipal": "Gestor municipal",
        "organismo_atencion": "Organismo de atencion",
        "administrador": "Administrador",
    }
    return render_template("dashboard.html",
                            role_label=ROLE_LABELS.get(session["usuario"]["rol"], session["usuario"]["rol"]))


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
