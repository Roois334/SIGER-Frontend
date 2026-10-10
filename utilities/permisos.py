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

    # --- Gestion de emergencias ---
    "emergencias.consultar":  {GESTOR_MUNICIPAL, ORGANISMO_ATENCION, ADMINISTRADOR},

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
