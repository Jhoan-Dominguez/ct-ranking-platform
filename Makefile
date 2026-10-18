VENV        ?= .venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
COMPOSE     := docker compose
APP_PORT    ?= $(shell grep -E '^APP_PORT=' .env 2>/dev/null | cut -d= -f2 || echo 8501)

.DEFAULT_GOAL := help
.PHONY: help create env install up down restart logs ps init-db seed-demo reset-db run dev \
        test lint format clean destroy

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- crear

create: env install ## Crea el proyecto: .env, dependencias y hooks de pre-commit
	$(VENV)/bin/pre-commit install
	@echo "✔ Proyecto creado. Siguiente paso: make up && make run"

env: ## Crea .env a partir de .env.example si no existe
	@test -f .env || (cp .env.example .env && echo "✔ .env creado")

install: ## Instala dependencias en el entorno virtual
	@test -x $(PYTHON) || python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements-dev.txt

# ---------------------------------------------------------------- subir / bajar

up: env ## Levanta PostgreSQL y Keycloak, espera a que estén listos e inicializa la BD
	$(COMPOSE) up -d
	$(PYTHON) scripts/wait_for_services.py
	$(PYTHON) -m app.db.init_db

down: ## Detiene y elimina los contenedores (conserva los datos)
	$(COMPOSE) down

restart: down up ## Reinicia los servicios

logs: ## Muestra los logs de los contenedores
	$(COMPOSE) logs -f --tail=100

ps: ## Estado de los contenedores
	$(COMPOSE) ps

run: ## Ejecuta la aplicación Streamlit
	$(VENV)/bin/streamlit run app/main.py --server.port $(APP_PORT)

dev: up run ## Levanta los servicios y ejecuta la aplicación

# ---------------------------------------------------------------- base de datos

init-db: ## Crea tablas y datos base (retos globales, admin)
	$(PYTHON) -m app.db.init_db

seed-demo: ## Carga usuarios y datos de demostración
	$(PYTHON) -m app.db.init_db --demo

reset-db: ## Borra y recrea todas las tablas de la app (¡pierde los datos!)
	$(PYTHON) -m app.db.init_db --reset

# ---------------------------------------------------------------- calidad

test: ## Ejecuta las pruebas (no requiere Docker)
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
