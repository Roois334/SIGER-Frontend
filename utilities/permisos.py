"""
Matriz central de roles y permisos de SIGER (copia del frontend).

IMPORTANTE: debe ser igual a utilities/permisos.py del BACKEND.
El backend es quien realmente protege los datos; aqui solo se usa para
mostrar/ocultar menus y redirigir antes de llamar a la API.
"""

CIUDADANO = "ciudadano"
GESTOR_MUNICIPAL = "gestor_municipal"
ORGANISMO_ATENCION = "organismo_atencion"
ADMINISTRADOR = "administrador"

ROLES_VALIDOS = [CIUDADANO, GESTOR_MUNICIPAL, ORGANISMO_ATENCION, ADMINISTRADOR]

# Roles cuyo alcance se limita al municipio que tienen asignado
# (solo ven las emergencias de SU municipio).
ROLES_CON_ALCANCE_MUNICIPAL = {GESTOR_MUNICIPAL, ORGANISMO_ATENCION}

PERMISOS = {
    # --- Ciudadano ---
    "reportes.crear":         {CIUDADANO},
    "reportes.ver_propios":   {CIUDADANO},

    # --- Mapa de emergencias: lo ven todos los roles (cada uno con su alcance) ---
    "mapa.ver":               {CIUDADANO, GESTOR_MUNICIPAL, ORGANISMO_ATENCION, ADMINISTRADOR},

    # --- Gestion de emergencias ---
    # Consultar: el gestor ve todo su municipio; el organismo SOLO lo que le asignaron.
    "emergencias.consultar":  {GESTOR_MUNICIPAL, ORGANISMO_ATENCION, ADMINISTRADOR},
    # Aceptar un reporte, asignarlo a un organismo o descartarlo
    "reportes.asignar":       {GESTOR_MUNICIPAL, ADMINISTRADOR},
    # Iniciar atencion, marcar resuelto o devolver un reporte asignado
    "reportes.atender":       {ORGANISMO_ATENCION},

    # --- Estadisticas (HU-17): el gestor ve su municipio; el administrador, todo ---
    "estadisticas.ver":       {GESTOR_MUNICIPAL, ADMINISTRADOR},
    # Dashboard general (HU-18): solo el administrador, con datos de toda la region
    "dashboard.ver":          {ADMINISTRADOR},

    # --- Administracion ---
    "usuarios.administrar":   {ADMINISTRADOR},
    "catalogos.administrar":  {ADMINISTRADOR},
}


def tiene_permiso(rol, permiso):
    return rol in PERMISOS.get(permiso, set())


def tiene_alcance_municipal(rol):
    return rol in ROLES_CON_ALCANCE_MUNICIPAL


def puede(usuario, permiso):
    """usuario = session['usuario'] (o None)."""
    return bool(usuario) and tiene_permiso(usuario.get("rol"), permiso)
