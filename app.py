import os
import time
from datetime import datetime
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, abort
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
            session["sync_ts"] = time.time()
            flash("Cuenta creada. Bienvenido a SIGER, " + payload["nombre"] + "!", "success")
            return redirect(url_for("dashboard"))

        flash(r.json().get("error", "No se pudo crear la cuenta"), "error")

    return render_template("registro.html", municipios=MUNICIPIOS_SABANA_OCCIDENTE)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html",
                            role_label=ROLE_LABELS.get(session["usuario"]["rol"], session["usuario"]["rol"]))


@app.route("/perfil")
@login_required
def perfil():
    return render_template("perfil.html",
                            role_label=ROLE_LABELS.get(session["usuario"]["rol"], session["usuario"]["rol"]))


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
    return render_template("admin_usuario_editar.html",
                            usuario=usuario, role_labels=ROLE_LABELS,
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
    "validado": "Validado",
    "asignado": "Asignado",
    "en_atencion": "En atención",
    "atendido": "Atendido",
    "cerrado": "Cerrado",
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
    return render_template("reporte_detalle.html", reporte=reporte,
                            nuevo=request.args.get("nuevo") == "1",
                            es_dueno=reporte["ciudadano_id"] == session["usuario"]["id"],
                            volver_endpoint=volver,
                            prioridad_labels=PRIORIDAD_LABELS, estado_labels=ESTADO_LABELS)


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


@app.route("/gestion/emergencias")
@permiso_required("emergencias.consultar")
def gestion_emergencias():
    alcance_municipal = tiene_alcance_municipal(session["usuario"]["rol"])
    filtros = {
        "q": request.args.get("q", "").strip(),
        "tipo": request.args.get("tipo", ""),
        "estado": request.args.get("estado", ""),
        "prioridad": request.args.get("prioridad", ""),
        "municipio_id": request.args.get("municipio_id", ""),
    }
    params = {k: v for k, v in filtros.items() if v}
    tipos = [t["nombre"] for t in _config_reporte()["tipos"]]

    def mostrar(reportes, municipios):
        return render_template("gestion_emergencias.html", reportes=reportes, municipios=municipios,
                                tipos=tipos, filtros=filtros, alcance_municipal=alcance_municipal,
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