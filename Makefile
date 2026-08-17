.PHONY: up down logs build test lint fmt typecheck check migrate shell psql clean seed \
        eval studio docs web web-install web-check web-types

# Published host ports are read back from Compose rather than guessed from the
# environment: API_PORT and WEB_PORT live in .env, which Compose reads and make
# does not, so a default here would print — and post to — the wrong port.
api_port = $$(docker compose port api 8000 2>/dev/null | cut -d: -f2)
web_port = $$(docker compose port web 80 2>/dev/null | cut -d: -f2)

# Overridable, and deliberately not read back from Compose: the documentation
# server is not one of its services.
DOCS_PORT ?= 3000

up:            ## Start the whole stack
	docker compose up -d --build
	@echo "Web on http://localhost:$(web_port)"
	@echo "API on http://localhost:$(api_port)  (OpenAPI at /docs)"

down:
	docker compose down

clean:         ## Stop and delete volumes (wipes the database)
	docker compose down -v

logs:
	docker compose logs -f api

build:
	docker compose build

test:          ## Run the test suite inside the api container
	docker compose run --rm api pytest -q

lint:
	docker compose run --rm api ruff check .

fmt:
	docker compose run --rm api ruff format .

typecheck:
	docker compose run --rm api mypy

check: lint typecheck test web-check   ## Everything CI runs

web-install:   ## Install frontend dependencies
	cd frontend && npm ci

web:           ## Frontend dev server with hot reload, against the running API
	cd frontend && npm run dev

web-check:     ## Frontend types, lint and production build
	cd frontend && npm run typecheck && npm run lint && npm run build

web-types:     ## Regenerate the API types from the running backend's OpenAPI document
	cd frontend && npm run types

seed:          ## Ingest the sample corpus
	@port=$(api_port); \
	if [ -z "$$port" ]; then \
		echo "the api container is not running — start it with 'make up'"; exit 1; \
	fi; \
	for f in data/transcripts/*.vtt; do \
		curl -fsS -X POST http://localhost:$$port/meetings -F "file=@$$f" > /dev/null \
			|| { echo "failed to ingest $$f"; exit 1; }; \
		echo "ingested $$f"; \
	done
	@echo "Uploads are accepted asynchronously; watch progress with 'make logs'."

eval:          ## Measure retrieval against the golden set — free and deterministic
	docker compose exec -T api python -m evals.run

# `--with` rather than a dev dependency: langgraph-cli is a tool, not something
# the application imports, and adding it to the project pins structlog down a
# minor version to satisfy langgraph-api. This installs it into a throwaway
# overlay on top of the project environment, so uv.lock stays the application's.
studio:        ## Open the graphs in LangGraph Studio, against the running database
	cd backend && uv run --with "langgraph-cli[inmem]" langgraph dev

# Docsify is a single-page application built entirely from static files, so any
# static server will do and the standard library already ships one. Nothing to
# install, and no Node needed for documentation.
docs:          ## Serve the documentation site
	@echo "Docs on http://localhost:$(DOCS_PORT)"
	@cd docs && python3 -m http.server $(DOCS_PORT)

migrate:       ## Apply migrations against the running database
	docker compose run --rm api alembic upgrade head

shell:
	docker compose exec api bash

psql:
	docker compose exec db psql -U postgres -d meetings
