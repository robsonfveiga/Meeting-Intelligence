.PHONY: up down logs build test lint fmt typecheck check migrate shell psql clean seed \
        eval eval-answers eval-facts eval-all

up:            ## Start the whole stack
	docker compose up -d --build
	@echo "API on http://localhost:8000  (docs at /docs)"

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

check: lint typecheck test   ## Everything CI runs

seed:          ## Ingest the sample corpus
	@for f in data/transcripts/*.vtt; do \
		curl -s -X POST http://localhost:$${API_PORT:-8000}/meetings -F "file=@$$f" > /dev/null; \
		echo "ingested $$f"; \
	done

eval:          ## Measure retrieval against the golden set — free and deterministic
	docker compose exec -T api python -m evals.run

eval-answers:  ## Measure the answer path. Calls the provider; costs money per run
	docker compose exec -T api python -m evals.run answers

eval-facts:    ## Measure extraction against a hand-written reading of the corpus
	docker compose exec -T api python -m evals.run facts

eval-all:      ## Every suite, plus the non-deterministic faithfulness judge
	docker compose exec -T api python -m evals.run all --judge

migrate:       ## Apply migrations against the running database
	docker compose run --rm api alembic upgrade head

shell:
	docker compose exec api bash

psql:
	docker compose exec db psql -U postgres -d meetings
