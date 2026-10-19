VENV        ?= .venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
# Motor de contenedores: docker o podman. Por defecto docker si está instalado, si no podman.
#   make up ENGINE=podman
ENGINE      ?= $(shell command -v docker >/dev/null 2>&1 && echo docker || echo podman)
ifeq ($(filter $(ENGINE),docker podman),)
$(error ENGINE debe ser docker o podman (recibido: "$(ENGINE)"))
endif
# Comando de compose de cada motor. Con Podman se puede usar el provider directamente:
#   make up ENGINE=podman PODMAN_COMPOSE=podman-compose
DOCKER_COMPOSE ?= docker compose
PODMAN_COMPOSE ?= podman compose
COMPOSE_CMD := $(if $(filter podman,$(ENGINE)),$(PODMAN_COMPOSE),$(DOCKER_COMPOSE))
# Archivos de cada motor: container/docker/ o container/podman/ (ver container/README.md).
CONTAINER_DIR := container/$(ENGINE)
COMPOSE     := $(COMPOSE_CMD) -p ct-ranking --env-file .env -f $(CONTAINER_DIR)/compose.yaml
COMPOSE_DEV := $(COMPOSE) -f $(CONTAINER_DIR)/compose.dev.yaml
# Comandos de una sola vez dentro de la imagen de la app (con la BD y Keycloak levantados).
APP_RUN     := $(COMPOSE) run --rm app
IMAGE       := localhost/ct-ranking-app:latest
BUILD_FILE  := $(CONTAINER_DIR)/$(if $(filter podman,$(ENGINE)),Containerfile,Dockerfile)

.DEFAULT_GOAL := help
.PHONY: help create env install check-env engine build image up dev run down restart logs ps shell \
        init-db \
        seed-demo reset-db purge-accounts migrate-emails test lint format clean destroy

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- crear

create: env install ## Prepara el entorno de desarrollo: .env, herramientas de calidad y pre-commit
	$(VENV)/bin/pre-commit install
	@echo "✔ Proyecto creado. Siguiente paso: make up"

env: ## Crea .env a partir de .env.example si no existe
	@test -f .env || (cp .env.example .env && echo "✔ .env creado")

install: ## Instala pytest, ruff, isort y pre-commit en .venv (la app corre en contenedores)
	@test -x $(PYTHON) || python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements-dev.txt

check-env: env
	@if grep -qE '^SMTP_HOST=(localhost|127\.0\.0\.1)' .env; then \
		echo "⚠ SMTP_HOST=localhost en .env: dentro del contenedor no llega a Mailpit."; \
		echo "  Usa SMTP_HOST=mailpit (o tu SMTP real). Ver .env.example."; fi

# ---------------------------------------------------------------- contenedores

engine: ## Muestra el motor y los archivos que se usarán (ENGINE=docker|podman)
	@echo "Motor:    $(ENGINE) ($$($(ENGINE) --version 2>/dev/null || echo 'no instalado'))"
	@v="$$($(COMPOSE_CMD) version 2>/dev/null | head -1)"; echo "Compose:  $(COMPOSE_CMD) ($${v:-no disponible})"
	@echo "Archivos: $(CONTAINER_DIR)/compose.yaml · $(BUILD_FILE)"

build: env ## Construye la imagen de la app con compose (python:3.13-slim)
	$(COMPOSE) build app

image: ## Construye la imagen sólo con docker/podman build, sin compose
	$(ENGINE) build -f $(BUILD_FILE) -t $(IMAGE) .

up: check-env build ## Levanta todo: PostgreSQL, Keycloak, Mailpit, configuración y la app
	$(COMPOSE) up -d db keycloak mailpit
	$(COMPOSE) --profile setup run --rm setup
	$(COMPOSE) up -d app
	@echo "✔ App en $$(grep -E '^APP_URL=' .env | cut -d= -f2-) · correos en http://localhost:8025"

dev: check-env build ## Como up, pero monta el código del host y recarga al guardar
	$(COMPOSE) up -d db keycloak mailpit
	$(COMPOSE) --profile setup run --rm setup
	$(COMPOSE_DEV) up -d app
	$(COMPOSE) logs -f app

run: check-env ## Reconstruye y reinicia sólo la app (tras cambiar código o dependencias)
	$(COMPOSE) up -d --build app

down: ## Detiene y elimina los contenedores (conserva los datos)
	$(COMPOSE) down

restart: down up ## Reinicia los servicios

logs: ## Muestra los logs de los contenedores
	$(COMPOSE) logs -f --tail=100

ps: ## Estado de los contenedores
	$(COMPOSE) ps

shell: ## Abre una terminal en un contenedor nuevo de la app
	$(APP_RUN) bash

# ---------------------------------------------------------------- base de datos

init-db: ## Crea tablas y datos base (retos globales, admin)
	$(APP_RUN) python -m app.database.init_db

seed-demo: ## Carga usuarios y datos de demostración
	$(APP_RUN) python -m app.database.init_db --demo

reset-db: ## Borra y recrea todas las tablas de la app (¡pierde los datos!)
	$(APP_RUN) python -m app.database.init_db --reset

purge-accounts: ## Elimina definitivamente las cuentas cuyo plazo de eliminación venció
	$(APP_RUN) python -m app.jobs.purge_accounts

migrate-emails: ## Pasa el correo de los estudiantes al dominio institucional (ARGS=--dry-run)
	$(APP_RUN) python -m scripts.migrate_student_emails $(ARGS)

# ---------------------------------------------------------------- calidad

test: ## Ejecuta las pruebas en .venv (SQLite en memoria, no requiere contenedores)
	$(PYTHON) -m pytest

lint: ## Ejecuta todos los hooks de pre-commit (isort, ruff, …)
	$(VENV)/bin/pre-commit run --all-files

format: ## Ordena imports y formatea el código
	$(VENV)/bin/isort app tests scripts
	$(VENV)/bin/ruff check --fix app tests scripts
	$(VENV)/bin/ruff format app tests scripts

# ---------------------------------------------------------------- limpieza

clean: ## Elimina cachés de Python y herramientas
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) \
		-not -path './$(VENV)/*' -prune -exec rm -rf {} +

destroy: ## Baja los servicios y BORRA los volúmenes (PostgreSQL y Keycloak)
	$(COMPOSE) down -v
