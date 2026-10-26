import os
import time
from datetime import datetime
from utilities.api import requests, SesionExpirada
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, abort, jsonify
from config import Config
from utilities.decorators import login_required, admin_required, permiso_required
from utilities.permisos import puede, tiene_alcance_municipal

app = Flask(__name__)
app.config.from_object(Config)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:5000")

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


@app.context_processor
def inject_backend_url():
    """Permite armar en las plantillas la URL completa de archivos servidos por el backend (ej. fotos de perfil)."""
    return {"backend_url": BACKEND_URL}


@app.context_processor
def inject_permisos():
    """En las plantillas: {% if puede('reportes.crear') %} ... {% endif %}"""
    usuario = session.get("usuario")
    return {"puede": lambda permiso: puede(usuario, permiso)}


MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


@app.template_filter("fecha_hora")
def filtro_fecha_hora(valor, con_hora=True):
    """'2026-10-10T14:43:00' -> '10 oct 2026 · 2:43 p. m.'"""
    if not valor:
        return "—"
    try:
        d = datetime.fromisoformat(valor[:19])
    except ValueError:
        return valor
    texto = f"{d.day} {MESES[d.month - 1]} {d.year}"
    if con_hora:
        h12 = d.hour % 12 or 12
        texto += f" · {h12}:{d.minute:02d} {'a. m.' if d.hour < 12 else 'p. m.'}"
    return texto


TIPOS_CON_TILDE = {
    "Inundacion": "Inundación",
    "Accidente de transito": "Accidente de tránsito",
    "Emergencia medica": "Emergencia médica",
}


@app.template_filter("tipo_bonito")
def filtro_tipo_bonito(tipo):
    """Los tipos se guardan sin tildes; aqui se muestran bien escritos."""
    return TIPOS_CON_TILDE.get(tipo, tipo)


@app.errorhandler(413)
def archivo_demasiado_grande(e):
    flash("Los archivos superan el tamano maximo permitido (10 MB por archivo, 5 archivos)", "error")
    return redirect(url_for("reportar_emergencia"))


# ---------------- Sincronizacion del usuario con el backend ----------------
# Si el administrador cambia el rol o desactiva una cuenta, la sesion del
# frontend se actualiza sola (cada INTERVALO_SYNC_SEG segundos como maximo).
RUTAS_SIN_SYNC = {"static", "index", "login", "registro", "logout"}
INTERVALO_SYNC_SEG = 60


@app.before_request
def sincronizar_usuario():
    if "usuario" not in session or request.endpoint in RUTAS_SIN_SYNC:
        return None
    if time.time() - session.get("sync_ts", 0) < INTERVALO_SYNC_SEG:
        return None

    try:
        r = requests.get(BACKEND_URL + "/api/usuarios/me", headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        return None

    if r.status_code in (401, 422):  # cuenta desactivada, token vencido o invalido
        session.clear()
        flash("Tu sesion expiro o tu cuenta fue desactivada. Ingresa de nuevo", "error")
        return redirect(url_for("login"))

    if r.status_code == 200:
        session["usuario"] = r.json()["usuario"]
        session["sync_ts"] = time.time()
    return None


@app.route("/")
def index():
    if "usuario" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


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
            session["sync_ts"] = time.time()
            flash("Bienvenido, " + data["usuario"]["nombre"] + "!", "success")
            return redirect(url_for("dashboard"))

        flash(r.json().get("error", "Correo o contrasena incorrectos"), "error")

    return render_template("login.html")


@app.route("/olvide-password", methods=["GET", "POST"])
def olvide_password():
    """Paso 1: el usuario escribe su correo y el backend le envia el enlace (Gmail)."""
    if "usuario" in session:
        return redirect(url_for("perfil", _anchor="seguridad"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        try:
            r = requests.post(BACKEND_URL + "/api/auth/olvide-password", json={"email": email}, timeout=10)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return render_template("olvide.html", estado="form", email=email)
        if r.status_code != 200:
            flash(r.json().get("error", "No se pudo enviar el correo"), "error")
            return render_template("olvide.html", estado="form", email=email)
        session["reset_email"] = email
        return redirect(url_for("olvide_password", enviado=1))

    email = session.get("reset_email", "")
    if request.args.get("nuevo"):
        session.pop("reset_email", None)
        email = ""
    elif request.args.get("enviado") and email:
        dominio = email.rsplit("@", 1)[-1]
        return render_template("olvide.html", estado="enviado", email=email,
                                es_gmail=dominio in ("gmail.com", "googlemail.com"))
    return render_template("olvide.html", estado="form", email="")


@app.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer_password(token):
    """Paso 2: el enlace del correo abre esta pantalla para crear la nueva contrasena."""
    if request.method == "POST":
        nueva = request.form.get("nueva", "")
        if nueva != request.form.get("confirmar", ""):
            flash("Las contrasenas no coinciden", "error")
            return redirect(url_for("restablecer_password", token=token))
        try:
            r = requests.post(BACKEND_URL + "/api/auth/restablecer", json={"token": token, "nueva": nueva}, timeout=8)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return redirect(url_for("restablecer_password", token=token))
        if r.status_code == 200:
            session.pop("reset_email", None)
            flash("Contrasena actualizada. Ya puedes ingresar con la nueva", "success")
            return redirect(url_for("login"))
        flash(r.json().get("error", "No se pudo restablecer la contrasena"), "error")
        return redirect(url_for("restablecer_password", token=token))

    try:
        r = requests.get(BACKEND_URL + f"/api/auth/restablecer/{token}", timeout=8)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return render_template("restablecer.html", valido=False)
    if r.status_code != 200:
        return render_template("restablecer.html", valido=False)
    info = r.json()
    return render_template("restablecer.html", valido=True, email=info.get("email"), minutos=info.get("minutos"))


TIPOS_DOCUMENTO = [
    ("CC", "Cédula de ciudadanía"),
    ("CE", "Cédula de extranjería"),
    ("TI", "Tarjeta de identidad"),
    ("PP", "Pasaporte"),
]


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
            "tipo_documento": request.form.get("tipo_documento", "").strip(),
            "documento": request.form.get("documento", "").strip(),
            "telefono": request.form.get("telefono", "").strip(),
            "password": request.form.get("password", ""),
        }
        confirmar = request.form.get("confirmar", "")

        if payload["password"] != confirmar:
            flash("Las contrasenas no coinciden", "error")
            return render_template("registro.html", municipios=MUNICIPIOS_SABANA_OCCIDENTE,
                           tipos_documento=TIPOS_DOCUMENTO, v=request.form)

        try:
            r = requests.post(BACKEND_URL + "/api/auth/register", json=payload, timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return render_template("registro.html", municipios=MUNICIPIOS_SABANA_OCCIDENTE,
                           tipos_documento=TIPOS_DOCUMENTO, v=request.form)

        if r.status_code == 201:
            data = r.json()
            session["usuario"] = data["usuario"]
            session["token"] = data["token"]
            session["sync_ts"] = time.time()
            flash("Cuenta creada. Bienvenido a SIGER, " + payload["nombre"] + "!", "success")
            return redirect(url_for("dashboard"))

        flash(r.json().get("error", "No se pudo crear la cuenta"), "error")

    return render_template("registro.html", municipios=MUNICIPIOS_SABANA_OCCIDENTE,
                           tipos_documento=TIPOS_DOCUMENTO, v=request.form)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html",
                            role_label=ROLE_LABELS.get(session["usuario"]["rol"], session["usuario"]["rol"]))


@app.route("/perfil")
@login_required
def perfil():
    miembro_desde = None
    try:
        r = requests.get(BACKEND_URL + "/api/usuarios/me", headers=_auth_headers(), timeout=5)
        if r.status_code == 200:
            datos = r.json()["usuario"]
            session["usuario"] = datos
            miembro_desde = datos.get("fecha_creacion")
    except requests.exceptions.ConnectionError:
        pass
    return render_template("perfil.html", miembro_desde=miembro_desde, tipos_documento=TIPOS_DOCUMENTO,
                            municipios=MUNICIPIOS_SABANA_OCCIDENTE,
                            role_label=ROLE_LABELS.get(session["usuario"]["rol"], session["usuario"]["rol"]))


def _perfil_accion(metodo, ruta, payload, mensaje_ok, ancla):
    """Llama al backend para un cambio del perfil y vuelve a la misma seccion con un aviso."""
    destino = url_for("perfil", _anchor=ancla)
    try:
        r = requests.request(metodo, BACKEND_URL + ruta, json=payload, headers=_auth_headers(), timeout=8)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(destino)
    if r.status_code == 200:
        session["usuario"] = r.json()["usuario"]
        flash(mensaje_ok, "success")
    else:
        try:
            flash(r.json().get("error", "No se pudo guardar el cambio"), "error")
        except ValueError:
            flash("No se pudo guardar el cambio", "error")
    return redirect(destino)


@app.route("/perfil/datos", methods=["POST"])
@login_required
def perfil_datos():
    payload = {"nombre": request.form.get("nombre", ""), "apellido": request.form.get("apellido", ""),
               "tipo_documento": request.form.get("tipo_documento", ""),
               "documento": request.form.get("documento", ""),
               "telefono": request.form.get("telefono", "")}
    if "municipio" in request.form:
        payload["municipio"] = request.form.get("municipio", "")
    return _perfil_accion("PUT", "/api/usuarios/me", payload, "Tus datos se guardaron", "datos")


@app.route("/perfil/correo", methods=["POST"])
@login_required
def perfil_correo():
    payload = {"email": request.form.get("email", ""), "password": request.form.get("password", "")}
    return _perfil_accion("PUT", "/api/usuarios/me/email", payload,
                          "Correo actualizado. Desde ahora ingresas con el nuevo", "correo")


@app.route("/perfil/password", methods=["POST"])
@login_required
def perfil_password():
    nueva = request.form.get("nueva", "")
    if nueva != request.form.get("confirmar", ""):
        flash("La confirmacion no coincide con la contrasena nueva", "error")
        return redirect(url_for("perfil", _anchor="seguridad"))
    payload = {"actual": request.form.get("actual", ""), "nueva": nueva}
    return _perfil_accion("PUT", "/api/usuarios/me/password", payload, "Contrasena actualizada", "seguridad")


@app.route("/perfil/foto/quitar", methods=["POST"])
@login_required
def perfil_foto_quitar():
    return _perfil_accion("DELETE", "/api/usuarios/me/foto", None, "Foto eliminada", "inicio")


@app.route("/perfil/foto", methods=["POST"])
@login_required
def perfil_foto():
    archivo = request.files.get("foto")
    if not archivo or not archivo.filename:
        flash("Selecciona una imagen primero", "error")
        return redirect(url_for("perfil"))

    try:
        r = requests.post(
            BACKEND_URL + "/api/usuarios/me/foto",
            headers=_auth_headers(),
            files={"foto": (archivo.filename, archivo.stream, archivo.mimetype)},
            timeout=10,
        )
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for("perfil"))

    if r.status_code == 200:
        session["usuario"] = r.json()["usuario"]
        flash("Foto de perfil actualizada", "success")
    else:
        flash(r.json().get("error", "No se pudo actualizar la foto"), "error")

    return redirect(url_for("perfil"))

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
            "organismo_id": request.form.get("organismo_id", ""),
        }
        try:
            r = requests.put(BACKEND_URL + f"/api/usuarios/{user_id}",
                              json=payload, headers=_auth_headers(), timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return redirect(url_for("admin_usuario_editar", user_id=user_id))

        if r.status_code == 200:
            session["sync_ts"] = 0  # por si el admin se edito a si mismo
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
    try:
        r_org = requests.get(BACKEND_URL + "/api/organismos", headers=_auth_headers(),
                              params={"estado": "activo"}, timeout=5)
        organismos = r_org.json().get("organismos", []) if r_org.status_code == 200 else []
    except requests.exceptions.ConnectionError:
        organismos = []
    return render_template("admin_usuario_editar.html",
                            usuario=usuario, role_labels=ROLE_LABELS, organismos=organismos,
                            municipios=MUNICIPIOS_SABANA_OCCIDENTE,
                            es_mi_cuenta=(usuario["id"] == session["usuario"]["id"]))


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

# ---------------- Municipios ----------------

@app.route("/admin/municipios", methods=["GET", "POST"])
@admin_required
def admin_municipios():
    if request.method == "POST":
        payload = {
            "codigo": request.form.get("codigo", "").strip(),
            "nombre": request.form.get("nombre", "").strip(),
        }
        try:
            r = requests.post(BACKEND_URL + "/api/municipios", json=payload, headers=_auth_headers(), timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return redirect(url_for("admin_municipios"))

        if r.status_code == 201:
            flash("Municipio creado correctamente", "success")
        else:
            flash(r.json().get("error", "No se pudo crear el municipio"), "error")
        return redirect(url_for("admin_municipios"))

    filtros = {
        "q": request.args.get("q", "").strip(),
        "estado": request.args.get("estado", ""),
    }
    params = {k: v for k, v in filtros.items() if v}

    try:
        r = requests.get(BACKEND_URL + "/api/municipios", headers=_auth_headers(), params=params, timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return render_template("admin_municipios.html", municipios=[], filtros=filtros)

    if r.status_code != 200:
        flash(r.json().get("error", "No se pudo cargar la lista de municipios"), "error")
        return render_template("admin_municipios.html", municipios=[], filtros=filtros)

    municipios = r.json().get("municipios", [])
    return render_template("admin_municipios.html", municipios=municipios, filtros=filtros)


@app.route("/admin/municipios/<int:municipio_id>/editar", methods=["GET", "POST"])
@admin_required
def admin_municipio_editar(municipio_id):
    if request.method == "POST":
        payload = {
            "codigo": request.form.get("codigo", "").strip(),
            "nombre": request.form.get("nombre", "").strip(),
        }
        try:
            r = requests.put(BACKEND_URL + f"/api/municipios/{municipio_id}",
                              json=payload, headers=_auth_headers(), timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return redirect(url_for("admin_municipio_editar", municipio_id=municipio_id))

        if r.status_code == 200:
            flash("Municipio actualizado correctamente", "success")
            return redirect(url_for("admin_municipios"))

        flash(r.json().get("error", "No se pudo actualizar el municipio"), "error")
        return redirect(url_for("admin_municipio_editar", municipio_id=municipio_id))

    try:
        r = requests.get(BACKEND_URL + f"/api/municipios/{municipio_id}", headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for("admin_municipios"))

    if r.status_code != 200:
        flash(r.json().get("error", "Municipio no encontrado"), "error")
        return redirect(url_for("admin_municipios"))

    municipio = r.json()["municipio"]
    return render_template("admin_municipio_editar.html", municipio=municipio)


@app.route("/admin/municipios/<int:municipio_id>/estado", methods=["POST"])
@admin_required
def admin_municipio_estado(municipio_id):
    nuevo_estado = request.form.get("activo") == "1"
    try:
        r = requests.patch(BACKEND_URL + f"/api/municipios/{municipio_id}/estado",
                            json={"activo": nuevo_estado}, headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for("admin_municipios"))

    if r.status_code == 200:
        flash("Municipio activado correctamente" if nuevo_estado else "Municipio desactivado correctamente", "success")
    else:
        flash(r.json().get("error", "No se pudo cambiar el estado del municipio"), "error")

    return redirect(url_for("admin_municipios"))


# ---------------- Organismos ----------------

@app.route("/admin/organismos", methods=["GET", "POST"])
@admin_required
def admin_organismos():
    if request.method == "POST":
        payload = {
            "codigo": request.form.get("codigo", "").strip(),
            "nombre": request.form.get("nombre", "").strip(),
            "tipo": request.form.get("tipo", "").strip(),
            "municipios": [int(i) for i in request.form.getlist("municipios")],
        }
        try:
            r = requests.post(BACKEND_URL + "/api/organismos", json=payload, headers=_auth_headers(), timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return redirect(url_for("admin_organismos"))

        if r.status_code == 201:
            flash("Organismo creado correctamente", "success")
        else:
            flash(r.json().get("error", "No se pudo crear el organismo"), "error")
        return redirect(url_for("admin_organismos"))

    filtros = {
        "q": request.args.get("q", "").strip(),
        "estado": request.args.get("estado", ""),
    }
    params = {k: v for k, v in filtros.items() if v}

    try:
        r_org = requests.get(BACKEND_URL + "/api/organismos", headers=_auth_headers(), params=params, timeout=5)
        r_mun = requests.get(BACKEND_URL + "/api/municipios", headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return render_template("admin_organismos.html", organismos=[], municipios=[], filtros=filtros)

    if r_org.status_code != 200:
        flash(r_org.json().get("error", "No se pudo cargar la lista de organismos"), "error")
        return render_template("admin_organismos.html", organismos=[], municipios=[], filtros=filtros)

    organismos = r_org.json().get("organismos", [])
    municipios = r_mun.json().get("municipios", []) if r_mun.status_code == 200 else []
    return render_template("admin_organismos.html", organismos=organismos, municipios=municipios, filtros=filtros)


@app.route("/admin/organismos/<int:organismo_id>/editar", methods=["GET", "POST"])
@admin_required
def admin_organismo_editar(organismo_id):
    if request.method == "POST":
        payload = {
            "codigo": request.form.get("codigo", "").strip(),
            "nombre": request.form.get("nombre", "").strip(),
            "tipo": request.form.get("tipo", "").strip(),
        }
        ids_municipios = [int(i) for i in request.form.getlist("municipios")]

        try:
            r = requests.put(BACKEND_URL + f"/api/organismos/{organismo_id}",
                              json=payload, headers=_auth_headers(), timeout=5)
            if r.status_code == 200:
                r = requests.put(BACKEND_URL + f"/api/organismos/{organismo_id}/municipios",
                                  json={"municipios": ids_municipios}, headers=_auth_headers(), timeout=5)
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return redirect(url_for("admin_organismo_editar", organismo_id=organismo_id))

        if r.status_code == 200:
            flash("Organismo actualizado correctamente", "success")
            return redirect(url_for("admin_organismos"))

        flash(r.json().get("error", "No se pudo actualizar el organismo"), "error")
        return redirect(url_for("admin_organismo_editar", organismo_id=organismo_id))

    try:
        r_org = requests.get(BACKEND_URL + f"/api/organismos/{organismo_id}", headers=_auth_headers(), timeout=5)
        r_mun = requests.get(BACKEND_URL + "/api/municipios", headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for("admin_organismos"))

    if r_org.status_code != 200:
        flash(r_org.json().get("error", "Organismo no encontrado"), "error")
        return redirect(url_for("admin_organismos"))

    organismo = r_org.json()["organismo"]
    municipios = r_mun.json().get("municipios", []) if r_mun.status_code == 200 else []
    ids_asociados = {m["id"] for m in organismo.get("municipios", [])}
    return render_template("admin_organismo_editar.html",
                            organismo=organismo, municipios=municipios, ids_asociados=ids_asociados)


@app.route("/admin/organismos/<int:organismo_id>/estado", methods=["POST"])
@admin_required
def admin_organismo_estado(organismo_id):
    nuevo_estado = request.form.get("activo") == "1"
    try:
        r = requests.patch(BACKEND_URL + f"/api/organismos/{organismo_id}/estado",
                            json={"activo": nuevo_estado}, headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for("admin_organismos"))

    if r.status_code == 200:
        flash("Organismo activado correctamente" if nuevo_estado else "Organismo desactivado correctamente", "success")
    else:
        flash(r.json().get("error", "No se pudo cambiar el estado del organismo"), "error")

    return redirect(url_for("admin_organismos"))

# ---------------- Reportes de emergencia ----------------

# Respaldo por si el backend no responde la configuracion (la fuente real es el backend)
TIPOS_EMERGENCIA = [
    "Incendio",
    "Inundacion",
    "Accidente de transito",
    "Deslizamiento",
    "Fuga o derrame de sustancias",
    "Emergencia medica",
    "Otro",
]
PRIORIDAD_POR_TIPO = {
    "Incendio": "alta", "Inundacion": "alta", "Accidente de transito": "media",
    "Deslizamiento": "alta", "Fuga o derrame de sustancias": "critica",
    "Emergencia medica": "critica", "Otro": "media",
}
CONFIG_REPORTE_RESPALDO = {
    "tipos": [{"nombre": t, "prioridad": PRIORIDAD_POR_TIPO[t]} for t in TIPOS_EMERGENCIA],
    "limites": {"max_evidencias": 5, "max_mb": 10, "max_afectados": 100000,
                "min_descripcion": 15, "max_descripcion": 2000, "max_direccion": 200},
    "extensiones": ["gif", "jpeg", "jpg", "mp4", "pdf", "png"],
    "region": {"lat_min": 4.3, "lat_max": 5.3, "lon_min": -75.0, "lon_max": -73.8},
}

PRIORIDAD_LABELS = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
    "critica": "Crítica",
}

ESTADO_LABELS = {
    "pendiente": "Pendiente",
    "asignado": "Asignado",
    "en_atencion": "En atención",
    "resuelto": "Resuelto",
    "cerrado": "Cerrado",
    "descartado": "Descartado",
}


def _config_reporte():
    """Tipos, prioridades y limites desde el backend (con respaldo local)."""
    try:
        r = requests.get(BACKEND_URL + "/api/reportes/configuracion", headers=_auth_headers(), timeout=5)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return CONFIG_REPORTE_RESPALDO


@app.route("/reportar-emergencia", methods=["GET", "POST"])
@permiso_required("reportes.crear")
def reportar_emergencia():
    config = _config_reporte()

    try:
        r_mun = requests.get(BACKEND_URL + "/api/municipios/activos", headers=_auth_headers(), timeout=5)
        municipios = r_mun.json().get("municipios", []) if r_mun.status_code == 200 else []
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        municipios = []

    # Municipio del usuario como sugerencia inicial
    municipio_usuario = next(
        (str(m["id"]) for m in municipios if m["nombre"] == session["usuario"].get("municipio")), "")

    def mostrar(form_data):
        return render_template("reportar_emergencia.html", config=config, municipios=municipios,
                                form_data=form_data, municipio_sugerido=municipio_usuario,
                                prioridad_labels=PRIORIDAD_LABELS)

    if request.method == "POST":
        form_data = {
            "tipo": request.form.get("tipo", ""),
            "municipio_id": request.form.get("municipio_id", ""),
            "direccion": request.form.get("direccion", "").strip(),
            "latitud": request.form.get("latitud", ""),
            "longitud": request.form.get("longitud", ""),
            "descripcion": request.form.get("descripcion", "").strip(),
            "afectados": request.form.get("afectados", "0"),
            "heridos": request.form.get("heridos", "0"),
        }

        archivos = [
            ("evidencias", (f.filename, f.stream, f.mimetype))
            for f in request.files.getlist("evidencias") if f and f.filename
        ]

        try:
            r = requests.post(
                BACKEND_URL + "/api/reportes",
                data=form_data,
                files=archivos if archivos else None,
                headers=_auth_headers(),
                timeout=30,
            )
        except requests.exceptions.ConnectionError:
            flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
            return mostrar(form_data)

        if r.status_code == 201:
            reporte = r.json()["reporte"]
            # Redirigir (patron POST/Redirect/GET): si el usuario recarga la pagina
            # NO se crea un reporte duplicado.
            return redirect(url_for("reporte_detalle", reporte_id=reporte["id"], nuevo=1))

        try:
            mensaje = r.json().get("error", "No se pudo registrar el reporte")
        except ValueError:
            mensaje = "No se pudo registrar el reporte"
        flash(mensaje, "error")
        return mostrar(form_data)

    return mostrar(None)


@app.route("/mis-reportes")
@permiso_required("reportes.ver_propios")
def mis_reportes():
    try:
        r = requests.get(BACKEND_URL + "/api/reportes", headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return render_template("mis_reportes.html", reportes=[], prioridad_labels=PRIORIDAD_LABELS,
                                estado_labels=ESTADO_LABELS)

    if r.status_code != 200:
        flash(r.json().get("error", "No se pudo cargar tus reportes"), "error")
        return render_template("mis_reportes.html", reportes=[], prioridad_labels=PRIORIDAD_LABELS,
                                estado_labels=ESTADO_LABELS)

    return render_template("mis_reportes.html", reportes=r.json().get("reportes", []),
                            prioridad_labels=PRIORIDAD_LABELS, estado_labels=ESTADO_LABELS)


@app.route("/reportes/<int:reporte_id>")
@login_required
def reporte_detalle(reporte_id):
    """
    Detalle de un reporte. Lo ven: su dueno, el administrador y los
    gestores/organismos del mismo municipio (el backend decide).
    """
    volver = "mis_reportes" if session["usuario"]["rol"] == "ciudadano" else "gestion_emergencias"
    try:
        r = requests.get(BACKEND_URL + f"/api/reportes/{reporte_id}", headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for(volver))

    if r.status_code != 200:
        flash("No se encontro el reporte o no tienes acceso a el", "error")
        return redirect(url_for(volver))

    reporte = r.json()["reporte"]
    tipos_cambio = []
    if reporte.get("acciones", {}).get("reclasificar"):
        tipos_cambio = [t["nombre"] for t in _config_reporte()["tipos"]]
    return render_template("reporte_detalle.html", reporte=reporte, tipos_cambio=tipos_cambio,
                            nuevo=request.args.get("nuevo") == "1",
                            es_dueno=reporte["ciudadano_id"] == session["usuario"]["id"],
                            volver_endpoint=volver,
                            prioridad_labels=PRIORIDAD_LABELS, estado_labels=ESTADO_LABELS)


def _accion_reporte(reporte_id, metodo_url, payload, mensaje_ok):
    """Llama al backend (asignar / cambiar estado) y vuelve al detalle con un aviso."""
    try:
        r = requests.post(BACKEND_URL + f"/api/reportes/{reporte_id}/{metodo_url}",
                          json=payload, headers=_auth_headers(), timeout=8)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return redirect(url_for("reporte_detalle", reporte_id=reporte_id))

    if r.status_code == 200:
        flash(mensaje_ok, "success")
    else:
        try:
            flash(r.json().get("error", "No se pudo completar la accion"), "error")
        except ValueError:
            flash("No se pudo completar la accion", "error")
    return redirect(url_for("reporte_detalle", reporte_id=reporte_id))


@app.route("/reportes/<int:reporte_id>/asignar", methods=["POST"])
@permiso_required("reportes.asignar")
def reporte_asignar(reporte_id):
    """El gestor acepta el reporte y lo asigna (o reasigna) a un organismo."""
    payload = {
        "organismo_id": request.form.get("organismo_id", type=int),
        "prioridad": request.form.get("prioridad", "").strip(),
        "comentario": request.form.get("comentario", "").strip(),
        "vias_afectadas": request.form.get("vias_afectadas", "").strip(),
        "area_afectada": request.form.get("area_afectada", "").strip(),
        "riesgo_propagacion": request.form.get("riesgo_propagacion", "").strip(),
    }
    return _accion_reporte(reporte_id, "asignar", payload,
                           "Reporte aceptado y asignado. El organismo ya puede verlo")


MENSAJES_ACCION = {
    "iniciar": "Atención iniciada. El ciudadano puede ver el avance",
    "resolver": "Reporte marcado como resuelto",
    "cerrar": "Emergencia cerrada. Quedó registrada en el historial",
    "devolver": "Reporte devuelto al gestor municipal",
    "descartar": "Reporte descartado",
}


@app.route("/reportes/<int:reporte_id>/estado", methods=["POST"])
@login_required
def reporte_estado(reporte_id):
    """Acciones: iniciar / resolver / devolver (organismo) y descartar (gestor). El backend valida."""
    accion = request.form.get("accion", "")
    if accion not in MENSAJES_ACCION:
        flash("Accion no valida", "error")
        return redirect(url_for("reporte_detalle", reporte_id=reporte_id))
    payload = {"accion": accion, "comentario": request.form.get("comentario", "").strip()}
    return _accion_reporte(reporte_id, "estado", payload, MENSAJES_ACCION[accion])


@app.route("/reportes/<int:reporte_id>/tipo", methods=["POST"])
@login_required
def reporte_tipo(reporte_id):
    """El gestor corrige el tipo de una emergencia abierta. El backend valida permisos y estado."""
    payload = {"tipo": request.form.get("tipo", "").strip(),
               "comentario": request.form.get("comentario", "").strip()}
    return _accion_reporte(reporte_id, "tipo", payload,
                           "Tipo de emergencia actualizado. Quedó registrado en el historial")


@app.route("/evidencias/<int:evidencia_id>")
@login_required
def ver_evidencia(evidencia_id):
    """
    Actua como intermediario: el navegador nunca habla directo con el backend
    (que exige un token Bearer), sino con esta ruta protegida por la sesion.
    """
    try:
        r = requests.get(BACKEND_URL + f"/api/reportes/evidencias/{evidencia_id}",
                          headers=_auth_headers(), timeout=15)
    except requests.exceptions.ConnectionError:
        abort(502)

    if r.status_code == 403:
        abort(403)
    if r.status_code == 404:
        abort(404)
    if r.status_code != 200:
        abort(502)

    respuesta = Response(r.content, mimetype=r.headers.get("Content-Type", "application/octet-stream"))
    respuesta.headers["Cache-Control"] = "private, max-age=3600"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


@app.route("/mapa")
def mapa_emergencias():
    """
    Mapa de emergencias. Los usuarios con sesion ven lo que les corresponde segun su rol;
    un visitante (sin cuenta) ve el mapa PUBLICO: emergencias confirmadas, sin datos privados.
    """
    municipios = MUNICIPIOS_SABANA_OCCIDENTE
    if "usuario" not in session:
        return render_template("mapa_emergencias.html", municipios=municipios, tipos=TIPOS_EMERGENCIA,
                                publico=True, alcance_municipal=False, es_organismo=False, es_ciudadano=False,
                                prioridad_labels=PRIORIDAD_LABELS, estado_labels=ESTADO_LABELS)
    if not puede(session["usuario"], "mapa.ver"):
        flash("No tienes permisos para acceder a esa seccion", "error")
        return redirect(url_for("dashboard"))
    rol = session["usuario"]["rol"]
    alcance_municipal = tiene_alcance_municipal(rol)
    tipos = [t["nombre"] for t in _config_reporte()["tipos"]]
    return render_template("mapa_emergencias.html", municipios=municipios, tipos=tipos,
                            publico=False, alcance_municipal=alcance_municipal, es_organismo=(rol == "organismo_atencion"),
                            es_ciudadano=(rol == "ciudadano"),
                            prioridad_labels=PRIORIDAD_LABELS, estado_labels=ESTADO_LABELS)


def _mapa_datos_publico():
    """Visitante sin cuenta: solo los datos publicos que entrega el backend."""
    try:
        r = requests.get(BACKEND_URL + "/api/publico/mapa", timeout=8)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "No se pudo conectar con el servidor"}), 503
    if r.status_code != 200:
        return jsonify({"error": "No se pudieron cargar las emergencias"}), 502
    reportes = [{
        "id": x["id"], "tipo": x["tipo"], "tipo_nombre": filtro_tipo_bonito(x["tipo"]),
        "prioridad": x["prioridad"], "estado": x["estado"],
        "latitud": x.get("latitud"), "longitud": x.get("longitud"),
        "municipio": x.get("municipio"), "fecha_hora": x.get("fecha_hora"),
    } for x in r.json().get("reportes", [])]
    respuesta = jsonify({"reportes": reportes})
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.route("/mapa/datos")
def mapa_datos():
    """
    JSON liviano para el mapa (se consulta cada 30 s). El backend ya filtra por rol:
    el gestor ve su municipio y el organismo solo lo que le asignaron.
    Sin sesion se entregan solo los datos publicos.
    """
    if "usuario" not in session:
        return _mapa_datos_publico()
    if not puede(session["usuario"], "mapa.ver"):
        return jsonify({"error": "No tienes permisos"}), 403
    try:
        # El ciudadano ve sus propios reportes; los demas roles, los de su alcance
        ruta = "/api/reportes" if session["usuario"]["rol"] == "ciudadano" else "/api/reportes/gestion"
        r = requests.get(BACKEND_URL + ruta, headers=_auth_headers(), timeout=8)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "No se pudo conectar con el servidor"}), 503

    if r.status_code in (401, 422):
        return jsonify({"error": "Tu sesion expiro. Ingresa de nuevo"}), 401
    if r.status_code != 200:
        try:
            mensaje = r.json().get("error", "No se pudieron cargar las emergencias")
        except ValueError:
            mensaje = "No se pudieron cargar las emergencias"
        return jsonify({"error": mensaje}), (r.status_code if r.status_code in (400, 403) else 502)

    reportes = []
    for x in r.json().get("reportes", []):
        reportes.append({
            "id": x["id"], "folio": x["folio"], "tipo": x["tipo"], "tipo_nombre": filtro_tipo_bonito(x["tipo"]),
            "prioridad": x["prioridad"], "estado": x["estado"],
            "latitud": x.get("latitud"), "longitud": x.get("longitud"),
            "direccion": x["direccion"], "municipio": x.get("municipio"),
            "fecha_hora": x.get("fecha_hora"), "organismo": x.get("organismo"),
            "afectados": x.get("afectados", 0),
            "descripcion": (x.get("descripcion") or "")[:160],
        })
    respuesta = jsonify({"reportes": reportes})
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.route("/gestion/emergencias")
@permiso_required("emergencias.consultar")
def gestion_emergencias():
    alcance_municipal = tiene_alcance_municipal(session["usuario"]["rol"])
    es_organismo = session["usuario"]["rol"] == "organismo_atencion"
    filtros = {
        "q": request.args.get("q", "").strip(),
        "tipo": request.args.get("tipo", ""),
        "estado": request.args.get("estado", ""),
        "prioridad": request.args.get("prioridad", ""),
        "municipio_id": request.args.get("municipio_id", ""),
        "desde": request.args.get("desde", "").strip(),
        "hasta": request.args.get("hasta", "").strip(),
    }
    params = {k: v for k, v in filtros.items() if v}
    tipos = [t["nombre"] for t in _config_reporte()["tipos"]]

    def mostrar(reportes, municipios):
        return render_template("gestion_emergencias.html", reportes=reportes, municipios=municipios,
                                tipos=tipos, filtros=filtros, alcance_municipal=alcance_municipal,
                                es_organismo=es_organismo,
                                prioridad_labels=PRIORIDAD_LABELS, estado_labels=ESTADO_LABELS)

    try:
        r_rep = requests.get(BACKEND_URL + "/api/reportes/gestion", headers=_auth_headers(), params=params, timeout=5)
        r_mun = requests.get(BACKEND_URL + "/api/municipios/activos", headers=_auth_headers(), timeout=5)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor. Intenta mas tarde", "error")
        return mostrar([], [])

    if r_rep.status_code != 200:
        flash(r_rep.json().get("error", "No se pudo cargar el listado de emergencias"), "error")
        return mostrar([], [])

    municipios = r_mun.json().get("municipios", []) if r_mun.status_code == 200 else []
    return mostrar(r_rep.json().get("reportes", []), municipios)


# ---------------------------------------------------------------------------
# Informacion de los organismos de atencion (pagina informativa para todos)
# ---------------------------------------------------------------------------
TIPOS_FILTRO_ORGANISMOS = [
    ("incendio", "Incendio"),
    ("inundacion", "Inundación"),
    ("transito", "Accidente de tránsito"),
    ("deslizamiento", "Deslizamiento"),
    ("fuga", "Fuga o derrame"),
    ("medica", "Emergencia médica"),
]

ORGANISMOS_INFO = [
    {"clave": "bomberos", "nombre": "Bomberos", "icono": "llama", "linea": "119",
     "resumen": "Combaten incendios y realizan rescates y control de emergencias con materiales peligrosos.",
     "funciones": ["Apagan incendios en viviendas, comercios y zonas rurales",
                   "Rescatan personas atrapadas en accidentes o estructuras",
                   "Controlan fugas de gas y sustancias peligrosas"],
     "cuando": "Humo o llamas, olor fuerte a gas, personas atrapadas.",
     "tipos": ["incendio", "fuga", "transito"]},
    {"clave": "cruzroja", "nombre": "Cruz Roja Colombiana", "icono": "cruz", "linea": "132",
     "resumen": "Brinda primeros auxilios, atención prehospitalaria y ayuda humanitaria a las familias afectadas.",
     "funciones": ["Atienden heridos y personas en riesgo de salud",
                   "Apoyan con ambulancias y socorro en accidentes",
                   "Entregan ayuda humanitaria tras una emergencia"],
     "cuando": "Personas lesionadas, familias damnificadas, necesidad de primeros auxilios.",
     "tipos": ["transito", "medica", "inundacion", "deslizamiento"]},
    {"clave": "defensacivil", "nombre": "Defensa Civil Colombiana", "icono": "escudo", "linea": "144",
     "resumen": "Apoya el rescate y la atención de desastres naturales y la evacuación de comunidades.",
     "funciones": ["Rescatan personas en inundaciones y deslizamientos",
                   "Evacúan y asisten a comunidades en riesgo",
                   "Apoyan la búsqueda y el salvamento"],
     "cuando": "Crecientes de ríos, derrumbes, personas aisladas o desaparecidas.",
     "tipos": ["inundacion", "deslizamiento"]},
    {"clave": "policia", "nombre": "Policía Nacional", "icono": "placa", "linea": "123",
     "resumen": "Garantiza la seguridad y el orden público en el lugar de la emergencia.",
     "funciones": ["Aseguran la zona y controlan el acceso",
                   "Atienden riñas, robos y situaciones de violencia",
                   "Apoyan accidentes con presencia de riesgo"],
     "cuando": "Hay riesgo para la seguridad de las personas o disturbios.",
     "tipos": ["transito"]},
    {"clave": "salud", "nombre": "Secretaría de Salud y Ambulancias", "icono": "pulso", "linea": "123",
     "resumen": "Atiende emergencias médicas y coordina el traslado de pacientes al hospital.",
     "funciones": ["Atienden urgencias médicas con ambulancia",
                   "Trasladan heridos a centros de salud",
                   "Coordinan la atención hospitalaria"],
     "cuando": "Pérdida de conciencia, dificultad para respirar, heridas graves.",
     "tipos": ["medica", "transito"]},
    {"clave": "transito", "nombre": "Tránsito y Transporte", "icono": "carro", "linea": None,
     "resumen": "Gestiona la movilidad y atiende los accidentes y bloqueos en las vías.",
     "funciones": ["Atienden accidentes y levantan el informe",
                   "Regulan el tráfico y habilitan rutas alternas",
                   "Retiran vehículos que obstruyen la vía"],
     "cuando": "Choques, vías bloqueadas, vehículos varados que ponen en riesgo.",
     "tipos": ["transito"]},
    {"clave": "gestionriesgo", "nombre": "Gestión del Riesgo", "icono": "alerta", "linea": None,
     "resumen": "Coordina la prevención y respuesta ante desastres en el municipio.",
     "funciones": ["Evalúan zonas de riesgo y emiten alertas",
                   "Coordinan a los demás organismos de respuesta",
                   "Gestionan ayudas y albergues temporales"],
     "cuando": "Inundaciones, deslizamientos, vendavales o zonas inestables.",
     "tipos": ["inundacion", "deslizamiento"]},
    {"clave": "servicios", "nombre": "Empresas de Servicios Públicos", "icono": "rayo", "linea": None,
     "resumen": "Atienden daños y fugas en las redes de gas, agua y energía.",
     "funciones": ["Reparan fugas de gas y daños en redes",
                   "Restablecen el servicio de agua y energía",
                   "Cortan el suministro cuando hay peligro"],
     "cuando": "Olor a gas, cables caídos, tuberías rotas.",
     "tipos": ["fuga"]},
    {"clave": "ambiental", "nombre": "Autoridad Ambiental (CAR)", "icono": "hoja", "linea": None,
     "resumen": "Protege el medio ambiente y actúa ante incendios forestales y contaminación.",
     "funciones": ["Atienden incendios de cobertura vegetal",
                   "Controlan derrames y contaminación de fuentes de agua",
                   "Evalúan el daño ambiental"],
     "cuando": "Incendios en cerros o bosques, derrames en ríos o suelos.",
     "tipos": ["incendio", "fuga"]},
]


@app.route("/organismos")
@login_required
def organismos_info():
    return render_template("organismos_info.html", organismos=ORGANISMOS_INFO,
                           tipos_filtro=TIPOS_FILTRO_ORGANISMOS)


# ---------------- Estadisticas (HU-17) ----------------

FILTROS_ESTADISTICAS = ("desde", "hasta", "municipio_id", "tipo", "prioridad", "estado")


def _params_estadisticas():
    return {k: request.args.get(k, "").strip() for k in FILTROS_ESTADISTICAS if request.args.get(k, "").strip()}


@app.route("/estadisticas")
@permiso_required("estadisticas.ver")
def estadisticas():
    es_admin = session["usuario"]["rol"] == "administrador"
    municipios = []
    if es_admin:
        try:
            r = requests.get(BACKEND_URL + "/api/municipios/activos", headers=_auth_headers(), timeout=6)
            if r.status_code == 200:
                municipios = r.json().get("municipios", [])
        except requests.exceptions.ConnectionError:
            pass
    tipos = [{"valor": t["nombre"], "texto": filtro_tipo_bonito(t["nombre"])} for t in _config_reporte()["tipos"]]
    return render_template("estadisticas.html", es_admin=es_admin, municipios=municipios, tipos=tipos,
                            filtros={k: request.args.get(k, "") for k in FILTROS_ESTADISTICAS},
                            prioridad_labels=PRIORIDAD_LABELS, estado_labels=ESTADO_LABELS,
                            municipio_propio=session["usuario"].get("municipio"))


@app.route("/tablero")
@permiso_required("dashboard.ver")
def tablero():
    """Dashboard general del administrador (HU-18). Usa los mismos datos que Estadisticas."""
    return render_template("tablero.html", prioridad_labels=PRIORIDAD_LABELS, estado_labels=ESTADO_LABELS)


@app.route("/estadisticas/datos")
@permiso_required("estadisticas.ver")
def estadisticas_datos():
    try:
        r = requests.get(BACKEND_URL + "/api/estadisticas", headers=_auth_headers(),
                         params=_params_estadisticas(), timeout=20)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "No se pudo conectar con el servidor"}), 503
    respuesta = jsonify(r.json() if r.status_code == 200 else {"error": r.json().get("error", "No se pudieron calcular las estadisticas")})
    respuesta.status_code = r.status_code if r.status_code in (200, 400, 403) else 502
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _fmt_min(m):
    if m is None:
        return "Sin datos"
    m = int(round(m))
    d, resto = divmod(m, 1440)
    h, mi = divmod(resto, 60)
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {mi} min"
    return f"{mi} min"


@app.route("/estadisticas/exportar")
@permiso_required("estadisticas.ver")
def estadisticas_exportar():
    """Descarga el informe de estadisticas (con los filtros aplicados) en PDF."""
    from utilities.pdf_estadisticas import generar
    try:
        r = requests.get(BACKEND_URL + "/api/estadisticas", headers=_auth_headers(),
                         params=_params_estadisticas(), timeout=20)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor", "error")
        return redirect(url_for("estadisticas"))
    if r.status_code != 200:
        flash(r.json().get("error", "No se pudieron generar las estadisticas"), "error")
        return redirect(url_for("estadisticas"))
    d = r.json()
    f = d["filtros"]
    es_admin = session["usuario"]["rol"] == "administrador"

    def _fecha(v):
        try:
            return datetime.strptime(v, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return v

    if f["desde"] and f["hasta"]:
        periodo = f"{_fecha(f['desde'])} al {_fecha(f['hasta'])}"
    elif f["desde"]:
        periodo = f"Desde el {_fecha(f['desde'])}"
    elif f["hasta"]:
        periodo = f"Hasta el {_fecha(f['hasta'])}"
    else:
        periodo = "Todo el historial"

    municipio = "Toda la región"
    if not es_admin:
        municipio = session["usuario"].get("municipio") or "Mi municipio"
    elif f["municipio_id"]:
        municipio = str(f["municipio_id"])
        try:
            rm = requests.get(BACKEND_URL + "/api/municipios/activos", headers=_auth_headers(), timeout=6)
            if rm.status_code == 200:
                for m in rm.json().get("municipios", []):
                    if str(m["id"]) == str(f["municipio_id"]):
                        municipio = m["nombre"]
        except requests.exceptions.ConnectionError:
            pass

    estado_txt = {"activas": "Activas", "resueltas": "Resueltas"}.get(f["estado"]) or ESTADO_LABELS.get(f["estado"], "Todos")
    info = {
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "es_admin": es_admin,
        "alcance": ("Toda la región de la Sabana de Occidente" if es_admin else "Municipio de " + municipio),
        "filtros": [("Periodo", periodo), ("Municipio", municipio),
                    ("Tipo", filtro_tipo_bonito(f["tipo"]) if f["tipo"] else "Todos"),
                    ("Prioridad", PRIORIDAD_LABELS.get(f["prioridad"], "Todas")), ("Estado", estado_txt)],
    }
    pdf = generar(d, info, _fmt_min, filtro_tipo_bonito,
                  lambda c: PRIORIDAD_LABELS.get(c, c), lambda c: ESTADO_LABELS.get(c, c))
    nombre = "siger-estadisticas-" + datetime.now().strftime("%Y%m%d-%H%M") + ".pdf"
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={nombre}", "Cache-Control": "no-store"})


# ---------------- Notificaciones (HU-15) ----------------

@app.route("/notificaciones")
@login_required
def notificaciones():
    solo = request.args.get("filtro") == "no_leidas"
    params = {"limite": 100}
    if solo:
        params["no_leidas"] = "1"
    try:
        r = requests.get(BACKEND_URL + "/api/notificaciones", headers=_auth_headers(), params=params, timeout=8)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor", "error")
        return render_template("notificaciones.html", notificaciones=[], no_leidas=0, solo=solo)
    if r.status_code != 200:
        flash(r.json().get("error", "No se pudieron cargar las notificaciones"), "error")
        return render_template("notificaciones.html", notificaciones=[], no_leidas=0, solo=solo)
    d = r.json()
    return render_template("notificaciones.html", notificaciones=d["notificaciones"],
                            no_leidas=d["no_leidas"], solo=solo)


@app.route("/notificaciones/resumen")
@login_required
def notificaciones_resumen():
    """JSON para la campana del menu (se consulta cada 30 s)."""
    try:
        r = requests.get(BACKEND_URL + "/api/notificaciones", headers=_auth_headers(),
                         params={"limite": 8}, timeout=6)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "sin conexion"}), 503
    if r.status_code != 200:
        return jsonify({"error": "no disponible"}), (401 if r.status_code in (401, 422) else 502)
    d = r.json()
    for n in d["notificaciones"]:
        n["url"] = url_for("notificacion_abrir", notificacion_id=n["id"])
    respuesta = jsonify(d)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.route("/notificaciones/<int:notificacion_id>/abrir")
@login_required
def notificacion_abrir(notificacion_id):
    """Marca la notificacion como leida y lleva al detalle de la emergencia."""
    destino = url_for("notificaciones")
    try:
        r = requests.post(BACKEND_URL + f"/api/notificaciones/{notificacion_id}/leer", headers=_auth_headers(), timeout=6)
        if r.status_code == 200:
            reporte_id = r.json().get("notificacion", {}).get("reporte_id")
            if reporte_id:
                destino = url_for("reporte_detalle", reporte_id=reporte_id)
    except requests.exceptions.ConnectionError:
        pass
    return redirect(destino)


@app.route("/notificaciones/leer-todas", methods=["POST"])
@login_required
def notificaciones_leer_todas():
    try:
        requests.post(BACKEND_URL + "/api/notificaciones/leer-todas", headers=_auth_headers(), timeout=6)
    except requests.exceptions.ConnectionError:
        flash("No se pudo conectar con el servidor", "error")
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("notificaciones"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesion cerrada correctamente", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------- seguridad
import secrets as _secrets


def _csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = _secrets.token_hex(32)
    return session["_csrf"]


@app.context_processor
def inject_csrf():
    """En los formularios: <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">"""
    return {"csrf_token": _csrf_token}


@app.before_request
def verificar_csrf():
    """Todo POST/PUT/PATCH/DELETE debe traer el token de la sesion (evita acciones forzadas desde otros sitios)."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    enviado = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
    esperado = session.get("_csrf", "")
    if not esperado or not _secrets.compare_digest(enviado.encode(), esperado.encode()):
        flash("Tu formulario expiro por seguridad. Intenta de nuevo", "error")
        return redirect(url_for("index"))
    return None


@app.errorhandler(SesionExpirada)
def sesion_expirada(e):
    session.clear()
    flash("Tu sesion expiro o tu cuenta fue desactivada. Ingresa de nuevo", "error")
    return redirect(url_for("login"))


@app.after_request
def no_guardar_en_cache(respuesta):
    """Las paginas HTML no se guardan en el cache del navegador: al cerrar sesion,
    el boton Atras no puede mostrar contenido privado."""
    if respuesta.mimetype == "text/html":
        respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        respuesta.headers["Pragma"] = "no-cache"
        respuesta.headers["Expires"] = "0"
    return respuesta


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=Config.DEBUG, port=5001)