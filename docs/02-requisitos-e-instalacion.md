# 2. Requisitos e instalación

## Software requerido

| Herramienta | Versión probada | Para qué se usa |
|-------------|-----------------|-----------------|
| **Docker** (Engine + plugin `docker compose`) **o Podman** (4.7+ con `podman-compose` 1.1+ o `docker-compose`) | Docker 29.x, Compose 5.6 | Construir la imagen de la app y ejecutar todos los servicios (`container/compose.yaml`). Ver [Docker y Podman](03-despliegue-y-operacion.md#docker-y-podman). |
| **GNU Make** | 4.x | Atajos de creación, arranque y parada (`Makefile`). |
| **Git** | cualquiera reciente | Control de versiones y hooks de pre-commit. |
| **Python** (opcional) | 3.13 (mínimo 3.12) | Sólo para las herramientas de calidad en `.venv`: pruebas, lint y formato. La app usa el Python de su imagen (`python:3.13-slim`). |

Requisitos de red y hardware aproximados:

- **Puertos libres en el host** (configurables en `.env`):
  - `5432`: PostgreSQL.
  - `8180`: Keycloak.
  - `1025` y `8025`: Mailpit (SMTP de desarrollo y bandeja web).
  - `8501`: Streamlit.
- **Descargas:**
  - En el primer `make up` se descargan las imágenes `python:3.13-slim`,
    `postgres:16-alpine` (~100 MB), `quay.io/keycloak/keycloak:26.4` (~450 MB) y
    `axllent/mailpit:v1.31.3` (~30 MB), y se instalan los paquetes de PyPI en la imagen de la app
    (queda en ~950 MB, sobre todo por pandas, pyarrow y plotly).
- **Memoria:** unos 1,5 GB libres. Keycloak consume ~700 MB, PostgreSQL ~50 MB y Streamlit
  ~200 MB.

> Las pruebas automáticas (`make test`) **no** necesitan contenedores: usan SQLite en memoria y
> el proveedor de autenticación local.

## Dependencias de Python

Están fijadas (versión exacta) en dos archivos:

| Archivo | Paquetes | Uso |
|---------|----------|-----|
| `requirements.txt` | `streamlit`, `SQLAlchemy`, `psycopg[binary]`, `bcrypt`, `requests`, `python-dotenv`, `pandas`, `plotly`, `pillow`, `authlib`, `httpx` | Ejecución de la aplicación. Se instala **en la imagen** (`container/Dockerfile`). `authlib` y `httpx` los usa `st.login` (inicio de sesión con Google). |
| `requirements-dev.txt` | Lo anterior + `pytest`, `ruff`, `isort`, `pre-commit` | Pruebas y calidad de código, en `.venv` (`make install`). |

## Instalación paso a paso

```bash
# 1. Clonar el repositorio y entrar a la carpeta
git clone <url> ct-ranking-platform && cd ct-ranking-platform

# 2. Levantar todo: imagen de la app, PostgreSQL, Keycloak, Mailpit, configuración y la app
make up           # crea .env si no existe; la app queda en http://localhost:8501

# 3. (Opcional) Cargar datos de demostración
make seed-demo

# 4. (Sólo para desarrollar) herramientas de calidad y hooks de pre-commit
make create
```

Para usar Podman aunque Docker esté instalado: `make up ENGINE=podman`.

Detalle de lo que hace cada paso:

1. **`make up`** ejecuta:
   - `make env`: copia `.env.example` a `.env` si `.env` no existe, y avisa si `SMTP_HOST` apunta
     a `localhost` (dentro del contenedor no llega a Mailpit).
   - `compose build app`: construye la imagen de la app desde `container/Dockerfile`.
   - `compose up -d db keycloak mailpit`: levanta los servicios.
   - `compose --profile setup run --rm setup`, que dentro de la imagen de la app ejecuta:
     - `python -m scripts.wait_for_services`: hace polling hasta que PostgreSQL acepta conexiones
       y Keycloak publica el realm `ct-ranking`. El tiempo máximo es 180 s.
     - `python -m scripts.configure_keycloak`: aplica al realm el servidor SMTP (para los correos
       de activación y de 2FA), las URLs de la app, el cliente de verificación de contraseña y el
       proveedor Google. Usa las credenciales de la consola (`KEYCLOAK_ADMIN`) y es idempotente.
     - `python -m app.database.init_db`: crea las tablas que falten, agrega las columnas, índices
       y restricciones nuevas a las tablas existentes, el usuario administrador local y los 10
       retos globales. Es idempotente.
   - `compose up -d app`: arranca la app. Al iniciar, el contenedor genera
     `~/.streamlit/secrets.toml` (configuración de `st.login`, permisos `600`, en el volumen
     `streamlit`) con `python -m scripts.write_streamlit_secrets` y ejecuta Streamlit.
   - Los scripts se ejecutan como módulos (`python -m scripts.<nombre>`) desde `/app`, así
     importan `app` sin modificar `sys.path`.
2. **`make seed-demo`** ejecuta `python -m app.database.init_db --demo` en un contenedor de la app.
   Ver [Datos iniciales y demo](11-datos-iniciales-y-demo.md).
3. **`make create`** ejecuta `make env`, `make install` (crea `.venv` e instala
   `requirements-dev.txt`) y `pre-commit install`.

## Variables de entorno (`.env`)

El contenedor de la app recibe `.env` como variables de entorno (`env_file`), y compose también lo
lee para configurar los demás contenedores (`--env-file .env`). Fuera de los contenedores,
`app/core/config.py` lo lee con `python-dotenv`. Las variables definidas en el entorno tienen
prioridad sobre las de `.env`.

Dentro de la red de compose, compose reemplaza para la app `POSTGRES_HOST` (`db`), `POSTGRES_PORT`
(`5432`), `KEYCLOAK_URL` (`http://keycloak:8080`) y vacía `DATABASE_URL`. Los valores de `.env`
para esas variables sólo sirven desde el host.

| Variable | Valor por defecto | Usada por | Descripción |
|----------|-------------------|-----------|-------------|
| `BIND_ADDRESS` | `127.0.0.1` | compose | Interfaz donde se publican los puertos de PostgreSQL, Keycloak, Mailpit y la app. Por defecto sólo este equipo; `0.0.0.0` los expone a la red. |
| `POSTGRES_USER` | `ctranking` | app, db, keycloak | Usuario de PostgreSQL. |
| `POSTGRES_PASSWORD` | `ctranking` | app, db, keycloak | Contraseña de PostgreSQL. |
| `POSTGRES_DB` | `ctranking` | app, db | Base de datos de la aplicación. |
| `POSTGRES_HOST` | `localhost` | host | Host de PostgreSQL visto desde el host. En el contenedor de la app, compose usa `db`. |
| `POSTGRES_PORT` | `5432` | compose | Puerto publicado de PostgreSQL en el host. |
| `DATABASE_URL` | *(vacío)* | app | URL completa de SQLAlchemy. Si se define, reemplaza a las `POSTGRES_*`. Ej.: `postgresql+psycopg://u:p@host:5432/db`. |
| `AUTH_PROVIDER` | `keycloak` | app | `keycloak` o `local` (ver [Autenticación](05-autenticacion.md)). |
| `KEYCLOAK_URL` | `http://localhost:8180` | host | URL de Keycloak vista desde el host. En el contenedor de la app, compose usa `http://keycloak:8080`. |
| `KEYCLOAK_PUBLIC_URL` | `http://localhost:8180` | Keycloak (`KC_HOSTNAME`) | URL de Keycloak que ve el navegador: emisor de los tokens y enlaces de los correos. |
| `KEYCLOAK_PORT` | `8180` | compose | Puerto del host donde se publica Keycloak. |
| `KEYCLOAK_REALM` | `ct-ranking` | app | Realm de la plataforma. |
| `KEYCLOAK_CLIENT_ID` | `ct-ranking-app` | app | Cliente confidencial usado por la app. |
| `KEYCLOAK_CLIENT_SECRET` | `ct-ranking-dev-secret` | app, keycloak | Secreto del cliente. Se inyecta en el realm al importarlo. |
| `KEYCLOAK_PWCHECK_CLIENT_ID` / `KEYCLOAK_PWCHECK_CLIENT_SECRET` | `ct-ranking-pwcheck` / `ct-ranking-pwcheck-dev-secret` | app, Keycloak | Cliente que sólo verifica usuario y contraseña (paso 1 del login con 2FA). Lo crea `configure_keycloak.py`. |
| `KEYCLOAK_ADMIN` | `admin` | keycloak | Usuario de la **consola** de Keycloak (realm `master`). |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | keycloak | Contraseña de la consola de Keycloak. |
| `APP_ADMIN_USERNAME` | `admin` | app, keycloak | Usuario administrador de **la plataforma**. |
| `APP_ADMIN_EMAIL` | `admin@ctranking.local` | app, keycloak | Correo del administrador. |
| `APP_ADMIN_PASSWORD` | `Admin123!` | app, keycloak | Contraseña del administrador de la plataforma. |
| `GRADE_MIN` | `0` | app | Nota mínima de la escala. |
| `GRADE_MAX` | `5` | app | Nota máxima de la escala. |
| `GRADE_PASSING` | `3` | app | Nota mínima aprobatoria y umbral de riesgo académico. |
| `APP_PORT` | `8501` | compose | Puerto del host donde se publica la app. Si cambia, cambia también `APP_URL`. |
| `APP_URL` | `http://localhost:8501` | app, Keycloak | URL pública de la app: enlaces de los correos y «Volver a la aplicación» en Keycloak. |
| `SMTP_HOST` / `SMTP_PORT` | `mailpit` / `1025` | app | Servidor SMTP con el que la app envía sus correos (Mailpit en desarrollo, visto desde el contenedor). |
| `SMTP_USER` / `SMTP_PASSWORD` | *(vacío)* | app, Keycloak | Credenciales SMTP (sólo con un servidor real). |
| `SMTP_STARTTLS` | `false` | app, Keycloak | `true` para servidores que usan STARTTLS (p. ej. puerto 587). |
| `MAIL_FROM` / `MAIL_FROM_NAME` | `no-reply@ctranking.local` / `CT Ranking` | app, Keycloak | Remitente de los correos. |
| `KEYCLOAK_SMTP_HOST` / `KEYCLOAK_SMTP_PORT` | `mailpit` / `1025` | Keycloak | SMTP visto **desde el contenedor** de Keycloak. |
| `MAILPIT_SMTP_PORT` / `MAILPIT_UI_PORT` | `1025` / `8025` | compose | Puertos del host donde se publican el SMTP y la bandeja web de Mailpit. |
| `MAIL_BACKEND` | `smtp` | app | `smtp` envía correos; `memory` los guarda en memoria (pruebas). |
| `ACCOUNT_DELETION_DAYS` | `7` | app | Días de espera antes de borrar definitivamente una cuenta. |
| `APP_SECRET_KEY` | *(vacío)* | app | Clave HMAC de los códigos que la app envía por correo. **Obligatoria en producción**; vacía, se usa `KEYCLOAK_CLIENT_SECRET` (sólo desarrollo). |
| `SESSION_TTL_HOURS` | `12` | app | Horas que dura una sesión iniciada con usuario y contraseña. `0` = sin límite. |
| `STUDENT_EMAIL_DOMAIN` | `estudiantes.areandina.edu.co` | app | Dominio obligatorio del correo de los **estudiantes** (registro y cambio de correo). Los administradores están exentos. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | *(vacío)* | Keycloak (vía `configure_keycloak.py`) | Credenciales OAuth de Google Cloud. Vacío = sin «Continuar con Google». Ver [Inicio de sesión con Google](15-inicio-sesion-con-google.md). |
| `AUTH_COOKIE_SECRET` | *(vacío → aleatorio)* | app (`secrets.toml`) | Secreto para firmar la cookie de sesión de `st.login`. Si queda vacío, se genera uno y se conserva en `secrets.toml` (volumen `streamlit`). |

> ⚠️ Hay **dos administradores distintos**. `KEYCLOAK_ADMIN` sirve para entrar a la consola de
> Keycloak (http://localhost:8180). `APP_ADMIN_USERNAME` sirve para entrar a la plataforma
> (http://localhost:8501).

> ⚠️ El realm de Keycloak sólo se importa la **primera vez** que arranca el contenedor con un
> volumen vacío. Después de eso, cambiar `APP_ADMIN_PASSWORD` o `KEYCLOAK_CLIENT_SECRET` en `.env`
> no modifica Keycloak. Haz el cambio en la consola de Keycloak o recrea los volúmenes con
> `make destroy && make up`.

## Configuración de Streamlit

`.streamlit/config.toml` se copia a la imagen y define:

- Color primario `#4F46E5`.
- Tamaño máximo de subida de 5 MB, usado por la foto de perfil.
- Desactiva la telemetría de uso.
- Barra de herramientas en modo mínimo.

## Verificación de la instalación

```bash
make ps                                   # db, keycloak, mailpit y app "running"/"healthy"
curl -s localhost:8180/realms/ct-ranking  # JSON del realm
curl -s localhost:8501/_stcore/health     # "ok"
make test                                 # todas las pruebas en verde
```
