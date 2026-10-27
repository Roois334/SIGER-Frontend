# SIGER – Frontend

**Sistema de Gestión de Emergencias Regional (Sabana de Occidente).** Interfaz web de SIGER hecha con Flask + Jinja
(renderizado en el servidor). Habla con el backend de SIGER por HTTP;
**no** accede a la base de datos.

> Levanta primero el backend (puerto 5000) y después este frontend (puerto 5001).

## Tecnologías

Python 3.12 · Flask 3 · Jinja2 · requests · HTML/CSS/JavaScript sin frameworks · Leaflet (mapas) con teselas de OpenStreetMap / CARTO · Nominatim (búsqueda de direcciones).

## Estructura

```
FRONTEND/
├── app.py                 # rutas y vistas
├── config.py              # configuración (clave secreta, cookies, tamaño de subida)
├── utilities/
│   ├── api.py             # envoltura de requests hacia el backend (timeouts, sesión vencida)
│   ├── decorators.py      # login_required, permiso_required, admin_required
│   └── permisos.py        # matriz de permisos por rol (la misma lógica que el backend)
├── templates/             # páginas (base.html es el layout común)
└── static/
    ├── css/               # style.css y estadisticas.css
    └── js/                # tema claro/oscuro, menú, gráficos de estadísticas
```

## Puesta en marcha

```powershell
cd FRONTEND
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre `http://127.0.0.1:5001`. Si ya tienes el entorno virtual del backend, también sirve usarlo
(`..\BACKEND\venv\Scripts\python app.py`).

### Variables de entorno (opcionales en desarrollo)

Este frontend **no** lee un archivo `.env`; usa las variables del sistema. Los valores por defecto funcionan en local.

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `BACKEND_URL` | `http://127.0.0.1:5000` | Dirección del backend. |
| `SECRET_KEY` | se genera sola y se guarda en `instance/secret_key.txt` | Firma de la sesión. En producción defínela tú. |
| `SESSION_COOKIE_SECURE` | `0` | Pon `1` cuando el sitio use HTTPS. |
| `FLASK_DEBUG` | `0` | `1` activa el modo depuración (solo desarrollo). |

En PowerShell: `$env:BACKEND_URL = "http://127.0.0.1:5000"` antes de `python app.py`.

## Qué ve cada rol

| Rol | Pantallas |
|---|---|
| Ciudadano | Registrar emergencia (con mapa y evidencias), Mis reportes (con fecha de actualización), detalle y seguimiento, Mapa de emergencias (sus reportes y las emergencias activas de la comunidad, con ubicación aproximada), Organismos de atención, Perfil. |
| Gestor municipal | Gestión de emergencias de su municipio (filtros por texto, tipo, estado, prioridad y fechas), aceptar/asignar, evaluar prioridad, cambiar tipo, descartar, cerrar, Mapa, Estadísticas. |
| Organismo de atención | Emergencias asignadas a su organismo, iniciar/resolver/devolver, Mapa, Estadísticas de lo asignado. |
| Administrador | Todo lo anterior sin límite de municipio, Resumen general en el panel, administración de usuarios, municipios y organismos. |

## Seguridad

- Sesión en cookie `HttpOnly` + `SameSite=Lax`; el token del backend vive en la sesión del servidor, nunca en el navegador.
- Protección CSRF propia: **todo formulario POST nuevo debe incluir** `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- Las páginas se sirven con `Cache-Control: no-store`: al cerrar sesión, el botón "atrás" no muestra contenido privado.
- Si el administrador cambia el rol o desactiva una cuenta, la sesión se sincroniza con el backend.
- Las evidencias se piden a través de una ruta propia protegida por la sesión.

## Notas

- Los textos de las pantallas están en español; los tipos de emergencia se guardan sin tildes y se muestran con ellas (filtro `tipo_bonito`).
- No hay pruebas automáticas todavía; las pantallas se probaron manualmente por rol.
