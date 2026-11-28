# Comandos comunes. El entorno virtual vive en non_local/ para que quede fuera del repositorio.
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/non_local/non_venv
COMPOSE := docker compose -p tp202620505 -f ops/docker/docker-compose.yml --env-file non_private/non_envs/.env

.PHONY: install db db-down test lint api graph web web-build web-test migrar crear-admin restablecer-admin respaldo-cuentas documentos corpus-estado corpus-seleccionar corpus-descargar corpus-curar corpus-indexar troceado-estado preguntar vocabulario vocabulario-estado

install:
	cd backend && uv sync

db:
	$(COMPOSE) up -d db

db-down:
	$(COMPOSE) down

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check src tests

api:
	cd backend && uv run uvicorn interfaces.api.app:app --reload

graph:
	cd backend && uv run python -m interfaces.jobs.load_graph

web:
	cd frontend && npm run dev

web-build:
	cd frontend && npm run build

web-test:
	cd frontend && npm run typecheck && npm test

migrar:
	cd backend && uv run python -m interfaces.jobs.accounts_admin migrar

crear-admin:
	cd backend && uv run python -m interfaces.jobs.accounts_admin crear-admin

restablecer-admin:
	cd backend && uv run python -m interfaces.jobs.accounts_admin restablecer-admin

respaldo-cuentas:
	cd backend && uv run python -m interfaces.jobs.accounts_admin respaldo

# procesa archivos o carpetas del corpus: make documentos ARCHIVOS=ruta [OPCIONES="--route structured --chunker fixed"]
documentos:
	cd backend && uv run python -m interfaces.jobs.documents procesar $(ARCHIVOS) $(OPCIONES)

# corpus documental (RAG)
corpus-estado:
	cd backend && uv run python -m interfaces.jobs.corpus estado

# cómo va la corrida de variantes de troceado (SEGUIR=si: se actualiza cada 30 s)
troceado-estado:
	pwsh -NoProfile -File ops/troceado_estado.ps1 $(if $(filter si,$(SEGUIR)),-Seguir)

corpus-seleccionar:
	cd backend && uv run python -m interfaces.jobs.corpus seleccionar

corpus-descargar:
	cd backend && uv run python -m interfaces.jobs.corpus descargar --lista completo

corpus-curar:
	cd backend && uv run python -m interfaces.jobs.corpus curar

corpus-indexar:
	cd backend && uv run python -m interfaces.jobs.corpus indexar

# make preguntar P="¿Cómo se maneja la Botrytis en arándano?"
preguntar:
	cd backend && uv run python -m interfaces.jobs.corpus preguntar "$(P)"

# vocabulario controlado (AGROVOC + nombres comunes de SIGIA)
vocabulario:
	cd backend && uv run python -m interfaces.jobs.vocabulary descargar

vocabulario-estado:
	cd backend && uv run python -m interfaces.jobs.vocabulary estado
