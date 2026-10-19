# Contenedores de CT Ranking

La app y sus servicios (PostgreSQL, Keycloak, Mailpit) corren en contenedores, con **Docker** o
con **Podman**. Cada motor tiene su carpeta; lo que comparten está en `common/`.

```
container/
├── common/
│   ├── keycloak/ct-ranking-realm.json   # realm que Keycloak importa en el primer arranque
│   └── postgres/01-create-keycloak-db.sql
├── docker/
│   ├── Dockerfile          # imagen de la app (python:3.13-slim)
│   ├── compose.yaml        # db, keycloak, mailpit, setup y app
│   └── compose.dev.yaml    # make dev: monta el código y recarga al guardar
└── podman/
    ├── Containerfile       # misma imagen, para Podman/Buildah
    ├── compose.yaml        # mismos servicios, ajustados a Podman
    └── compose.dev.yaml
```

`Dockerfile` y `Containerfile` tienen el mismo contenido, y los dos `compose.yaml` sólo difieren
en lo que se explica abajo. **Si cambias uno, cambia el otro.** El contexto de compilación es la
raíz del repositorio y el `.dockerignore` de la raíz (Docker y Podman lo leen) deja fuera `.env`,
`.venv` y demás.

## Uso con `make`

El Makefile elige la carpeta según `ENGINE` (por defecto `docker` si está instalado, si no
`podman`):

```bash
make engine                 # muestra motor, compose y archivos que se usarán
make up                     # Docker
make up ENGINE=podman       # Podman
make up ENGINE=podman PODMAN_COMPOSE=podman-compose   # usar el provider directamente
```

Todos los comandos aceptan `ENGINE`: `up`, `dev`, `run`, `down`, `logs`, `ps`, `shell`,
`init-db`, `seed-demo`, `reset-db`, `purge-accounts`, `migrate-emails`, `build`, `image` y
`destroy`.

## Sin `make`

Desde la raíz del repositorio:

```bash
# Docker
docker compose -p ct-ranking --env-file .env -f container/docker/compose.yaml up -d db keycloak mailpit
docker compose -p ct-ranking --env-file .env -f container/docker/compose.yaml --profile setup run --rm setup
docker compose -p ct-ranking --env-file .env -f container/docker/compose.yaml up -d --build app

# Podman
podman compose -p ct-ranking --env-file .env -f container/podman/compose.yaml up -d db keycloak mailpit
podman compose -p ct-ranking --env-file .env -f container/podman/compose.yaml --profile setup run --rm setup
podman compose -p ct-ranking --env-file .env -f container/podman/compose.yaml up -d --build app
```

`--env-file .env` es necesario porque compose busca `.env` junto al archivo de compose, no en la
raíz.

Sólo la imagen, sin compose:

```bash
docker build -f container/docker/Dockerfile -t localhost/ct-ranking-app .      # o: make image
podman build -f container/podman/Containerfile -t localhost/ct-ranking-app .   # o: make image ENGINE=podman
```

## Probar con Podman

1. **Instalar Podman** (4.7 o superior, para tener `podman compose`) y **podman-compose**
   (1.1 o superior):

   ```bash
   sudo dnf install podman podman-compose        # Fedora / RHEL
   sudo apt install podman podman-compose        # Debian 13
   # Ubuntu 24.04 trae podman-compose 1.0.6 (antiguo): instala podman con apt y el provider así
   sudo apt install podman pipx && pipx install podman-compose
   podman --version && podman compose version
   ```

2. **Usar puertos libres.** Si Docker sigue corriendo el proyecto, los puertos 5432, 8180, 1025,
   8025 y 8501 están ocupados. Detén Docker primero (`make down ENGINE=docker`) o usa otros
   puertos en `.env` (`POSTGRES_PORT`, `KEYCLOAK_PORT` + `KEYCLOAK_PUBLIC_URL`,
   `MAILPIT_SMTP_PORT`, `MAILPIT_UI_PORT`, `APP_PORT` + `APP_URL`).

3. **Levantar todo:**

   ```bash
   make up ENGINE=podman
   make ps ENGINE=podman            # db, keycloak, mailpit y app
   curl -s localhost:8501/_stcore/health   # "ok"
   ```

4. **Comprobar:** entrar a http://localhost:8501 con `admin` / `Admin123!`, ver los correos en
   http://localhost:8025, y opcionalmente `make seed-demo ENGINE=podman`.

5. **Bajar:** `make down ENGINE=podman` (o `make destroy ENGINE=podman` para borrar los volúmenes).

Docker y Podman guardan imágenes y volúmenes por separado: con Podman se empieza con la base de
datos vacía. Para llevar los datos, respalda con un motor y restaura con el otro (ver
`docs/03-despliegue-y-operacion.md#respaldo-y-restauración`).

## Diferencias de la versión de Podman

| Tema | Docker (`docker/`) | Podman (`podman/`) | Por qué |
|------|--------------------|--------------------|---------|
| Archivo de imagen | `Dockerfile` | `Containerfile` | Nombre nativo de Podman/Buildah (mismo contenido). |
| Pods | — | `x-podman: in_pod: false` | podman-compose mete los servicios en un pod por defecto; fuera de él, `compose run` y los puertos funcionan igual que en Docker. |
| Orden de arranque | `depends_on` con `condition: service_healthy` | `depends_on` simple | Sin systemd (WSL, algunos contenedores) Podman no ejecuta los healthchecks periódicos y la espera no terminaría. Keycloak se reinicia solo si arranca antes que PostgreSQL y `setup` espera a ambos. |

Reglas comunes que hacen falta para Podman y que la versión de Docker también cumple:

- **Nombres de imagen completos** (`docker.io/...`, `quay.io/...`, `localhost/...`): Podman no
  resuelve nombres cortos sin configurar `registries.conf`.
- **Bind mounts con `z`**: con SELinux (Fedora, RHEL) el contenedor no puede leerlos sin la
  etiqueta. Sin SELinux no tiene efecto.
- **La app nunca escribe en carpetas del host**: con Podman *rootless* los archivos montados
  aparecen con otro dueño dentro del contenedor. `secrets.toml` va a un volumen y los montajes de
  `make dev` son de sólo lectura.
- **Healthcheck en compose, no en la imagen**: Podman ignora `HEALTHCHECK` con el formato de
  imagen OCI.
- **Recarga en `make dev` por sondeo** (`STREAMLIT_SERVER_FILE_WATCHER_TYPE=poll`): en macOS y
  Windows, Docker Desktop y `podman machine` corren en una VM y los cambios de archivos montados
  no siempre generan eventos.
