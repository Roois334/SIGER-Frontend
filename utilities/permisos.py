CIUDADANO = "ciudadano"
GESTOR_MUNICIPAL = "gestor_municipal"
ORGANISMO_ATENCION = "organismo_atencion"
ADMINISTRADOR = "administrador"


ROLES_CON_ALCANCE_MUNICIPAL = {GESTOR_MUNICIPAL, ORGANISMO_ATENCION}

PERMISOS = {
    "reportes.crear":         {CIUDADANO},
    "reportes.ver_propios":   {CIUDADANO},

    "mapa.ver":               {CIUDADANO, GESTOR_MUNICIPAL, ORGANISMO_ATENCION, ADMINISTRADOR},

    "emergencias.consultar":  {GESTOR_MUNICIPAL, ORGANISMO_ATENCION, ADMINISTRADOR},
    "reportes.asignar":       {GESTOR_MUNICIPAL, ADMINISTRADOR},
    "reportes.atender":       {ORGANISMO_ATENCION},

    "estadisticas.ver":       {GESTOR_MUNICIPAL, ADMINISTRADOR},
    "dashboard.ver":          {ADMINISTRADOR},

    "usuarios.administrar":   {ADMINISTRADOR},
    "catalogos.administrar":  {ADMINISTRADOR},
}


def tiene_permiso(rol, permiso):
    return rol in PERMISOS.get(permiso, set())


def tiene_alcance_municipal(rol):
    return rol in ROLES_CON_ALCANCE_MUNICIPAL


def puede(usuario, permiso):
    return bool(usuario) and tiene_permiso(usuario.get("rol"), permiso)
