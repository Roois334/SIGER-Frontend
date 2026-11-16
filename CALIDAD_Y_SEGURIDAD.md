# Calidad y seguridad del FRONTEND

## 1. La contrasena y la red (HTTPS)

La contrasena viaja en dos tramos y los dos deben ir cifrados:

1. **Navegador -> frontend.** `utilities/seguridad.py` rechaza el trafico HTTP que llega por el proxy de Azure: los `GET` se redirigen a HTTPS y los `POST` (login, registro, cambio de contrasena) se rechazan con **426 sin procesarlos**. Ademas envia HSTS y marca `no-store` en `/login`, `/registro`, `/olvide-password`, `/restablecer` y `/perfil`.
2. **Frontend -> backend.** `BACKEND_URL` a un servidor remoto por `http://` se corrige solo a `https://` (queda un aviso en el log), y `utilities/api.py` **se niega a enviar** cualquier peticion por HTTP a un servidor que no sea la propia maquina.

La cookie de sesion lleva `Secure` automaticamente cuando `BACKEND_URL` no es local (`SESSION_COOKIE_SECURE=0/1` manda sobre esa regla).

**En Azure (una sola vez):**
```bash
az webapp update -g siger-rg -n siger-frontend-2716 --https-only true
az webapp config set -g siger-rg -n siger-frontend-2716 --min-tls-version 1.2
```
con `BACKEND_URL=https://siger-backend-2716.azurewebsites.net` en la configuracion de la app.

> `instance/secret_key.txt` es la clave que firma las sesiones. No se sube a Git (esta en `.gitignore`), pero si ya la compartiste en un ZIP, define `SECRET_KEY` en Azure con otro valor y borra ese archivo.

## 2. Pruebas, CI y SonarQube

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest --cov --cov-config=.coveragerc --cov-report=term-missing
```
`.github/workflows/ci.yml` compila, prueba y analiza con SonarQube en cada Pull Request y push; `publicar-azure.yml` lo ejecuta primero y solo despliega si pasa.
Configuracion de SonarQube: crea el proyecto `siger-frontend` y los secretos `SONAR_TOKEN` y `SONAR_HOST_URL` en GitHub (ver `CALIDAD_Y_SEGURIDAD.md` del backend, seccion 4).
La meta de 70 % de cobertura aplica al backend; aqui las pruebas cubren la seguridad del login y del transporte.
