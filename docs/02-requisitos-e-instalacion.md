# 2. Requisitos e instalación

## Software requerido

| Herramienta | Versión probada | Para qué se usa |
|-------------|-----------------|-----------------|
| **Python** | 3.13 (mínimo 3.12) | Ejecutar la aplicación Streamlit, los scripts y las pruebas. |
| **Docker Engine** | 29.x | Ejecutar PostgreSQL y Keycloak. |
| **Docker Compose** (plugin `docker compose`) | v2+ (probado con 5.6) | Orquestar los contenedores definidos en `docker-compose.yml`. |
| **GNU Make** | 4.x | Atajos de creación, arranque y parada (`Makefile`). |
| **Git** | cualquiera reciente | Control de versiones y hooks de pre-commit. |

Requisitos de red y hardware aproximados:

- **Puertos libres en el host** (configurables en `.env`):
  - `5432`: PostgreSQL.
  - `8180`: Keycloak.
  - `8501`: Streamlit.
- **Descargas:**
  - Durante la instalación se descargan los paquetes de PyPI.
  - En el primer `make up` se descargan las imágenes `postgres:16-alpine` (~100 MB) y
    `quay.io/keycloak/keycloak:26.4` (~450 MB).
- **Memoria:** unos 1,5 GB libres. Keycloak consume ~700 MB, PostgreSQL ~50 MB y Streamlit
  ~200 MB.

> Las pruebas automáticas (`make test`) **no** necesitan Docker: usan SQLite en memoria y el
> proveedor de autenticación local.

## Dependencias de Python

Están fijadas (versión exacta) en dos archivos:

| Archivo | Paquetes | Uso |
|---------|----------|-----|
| `requirements.txt` | `streamlit`, `SQLAlchemy`, `psycopg[binary]`, `bcrypt`, `requests`, `python-dotenv`, `pandas`, `plotly`, `pillow` | Ejecución de la aplicación. |
| `requirements-dev.txt` | Lo anterior + `pytest`, `ruff`, `isort`, `pre-commit` | Desarrollo, pruebas y calidad de código. |

El entorno virtual vive en `.venv/` (ya existía en el proyecto). Todas las dependencias se
instalan ahí; el Makefile siempre usa `.venv/bin/python`.

## Instalación paso a paso

```bash
# 1. Clonar el repositorio y entrar a la carpeta
git clone <url> ct-ranking-platform && cd ct-ranking-platform

# 2. Crear el proyecto: .env, entorno virtual, dependencias y hooks de pre-commit
make create

# 3. (Opcional) Revisar y ajustar .env: puertos, contraseñas, escala de notas

# 4. Levantar PostgreSQL y Keycloak, esperar a que estén listos y crear las tablas
make up

# 5. (Opcional) Cargar datos de demostración
make seed-demo

# 6. Ejecutar la aplicación
make run          # abre http://localhost:8501
```

Detalle de lo que hace cada paso:

1. **`make create`** ejecuta:
   - `make env`: copia `.env.example` a `.env` si `.env` no existe.
   - `make install`: crea `.venv` si falta y luego instala `requirements-dev.txt`.
   - `pre-commit install`: instala el hook en `.git/hooks/pre-commit`.
2. **`make up`** ejecuta:
   - `docker compose up -d`: levanta los contenedores `db` y `keycloak`.
   - `scripts/wait_for_services.py`: hace polling hasta que PostgreSQL acepta conexiones y
     Keycloak publica el realm `ct-ranking`. El tiempo máximo es 180 s.
   - `python -m app.db.init_db`: crea las tablas que falten, el usuario administrador local y
     los 10 retos globales. Es idempotente.
3. **`make seed-demo`** ejecuta `python -m app.db.init_db --demo`. Ver
   [Datos iniciales y demo](11-datos-iniciales-y-demo.md).
4. **`make run`** ejecuta `streamlit run app/main.py --server.port $APP_PORT`.

## Variables de entorno (`.env`)

`app/config.py` lee el archivo `.env` con `python-dotenv`. `docker compose` también lo lee
para configurar los contenedores. Las variables definidas en el entorno del sistema tienen
prioridad sobre las de `.env`.

| Variable | Valor por defecto | Usada por | Descripción |
|----------|-------------------|-----------|-------------|
| `POSTGRES_USER` | `ctranking` | app, db, keycloak | Usuario de PostgreSQL. |
| `POSTGRES_PASSWORD` | `ctranking` | app, db, keycloak | Contraseña de PostgreSQL. |
| `POSTGRES_DB` | `ctranking` | app, db | Base de datos de la aplicación. |
| `POSTGRES_HOST` | `localhost` | app | Host de PostgreSQL visto desde la app. |
| `POSTGRES_PORT` | `5432` | app, compose | Puerto publicado de PostgreSQL. |
| `DATABASE_URL` | *(vacío)* | app | URL completa de SQLAlchemy. Si se define, reemplaza a las `POSTGRES_*`. Ej.: `postgresql+psycopg://u:p@host:5432/db`. |
| `AUTH_PROVIDER` | `keycloak` | app | `keycloak` o `local` (ver [Autenticación](05-autenticacion.md)). |
| `KEYCLOAK_URL` | `http://localhost:8180` | app | URL base de Keycloak vista desde la app. |
| `KEYCLOAK_PORT` | `8180` | compose | Puerto del host donde se publica Keycloak. |
| `KEYCLOAK_REALM` | `ct-ranking` | app | Realm de la plataforma. |
| `KEYCLOAK_CLIENT_ID` | `ct-ranking-app` | app | Cliente confidencial usado por la app. |
| `KEYCLOAK_CLIENT_SECRET` | `ct-ranking-dev-secret` | app, keycloak | Secreto del cliente. Se inyecta en el realm al importarlo. |
| `KEYCLOAK_ADMIN` | `admin` | keycloak | Usuario de la **consola** de Keycloak (realm `master`). |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | keycloak | Contraseña de la consola de Keycloak. |
| `APP_ADMIN_USERNAME` | `admin` | app, keycloak | Usuario administrador de **la plataforma**. |
| `APP_ADMIN_EMAIL` | `admin@ctranking.local` | app, keycloak | Correo del administrador. |
| `APP_ADMIN_PASSWORD` | `Admin123!` | app, keycloak | Contraseña del administrador de la plataforma. |
| `GRADE_MIN` | `0` | app | Nota mínima de la escala. |
| `GRADE_MAX` | `5` | app | Nota máxima de la escala. |
| `GRADE_PASSING` | `3` | app | Nota mínima aprobatoria y umbral de riesgo académico. |
| `APP_PORT` | `8501` | Makefile | Puerto de Streamlit. |

> ⚠️ Hay **dos administradores distintos**. `KEYCLOAK_ADMIN` sirve para entrar a la consola de
> Keycloak (http://localhost:8180). `APP_ADMIN_USERNAME` sirve para entrar a la plataforma
> (http://localhost:8501).

> ⚠️ El realm de Keycloak sólo se importa la **primera vez** que arranca el contenedor con un
> volumen vacío. Después de eso, cambiar `APP_ADMIN_PASSWORD` o `KEYCLOAK_CLIENT_SECRET` en `.env`
> no modifica Keycloak. Haz el cambio en la consola de Keycloak o recrea los volúmenes con
> `make destroy && make up`.

## Configuración de Streamlit

`.streamlit/config.toml` define:

- Color primario `#4F46E5`.
- Tamaño máximo de subida de 5 MB, usado por la foto de perfil.
- Desactiva la telemetría de uso.
- Barra de herramientas en modo mínimo.

## Verificación de la instalación

```bash
make ps                                   # ambos contenedores "running"
curl -s localhost:8180/realms/ct-ranking  # JSON del realm
curl -s localhost:8501/_stcore/health     # "ok" (con make run activo)
make test                                 # todas las pruebas en verde
```
