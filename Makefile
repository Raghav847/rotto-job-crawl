.PHONY: crawl db-init test

FIXTURE_HOST_PATH = $(if $(filter /%,$(firstword $(FIXTURE_PATH))),$(FIXTURE_PATH),$(CURDIR)/$(FIXTURE_PATH))

crawl:
	docker compose run --build --rm --no-deps crawler

db-init:
	docker compose run --build --rm --no-deps crawler uv run --locked --offline python -m crawler.database

test:
	docker compose run --rm --no-deps $(if $(FIXTURE_PATH),-v "$(FIXTURE_HOST_PATH):/fixture/lifecycle.json:ro" -e FIXTURE_PATH=/fixture/lifecycle.json,) crawler uv run --locked --offline python -m tests.lifecycle
	docker compose run --rm --no-deps crawler uv run --locked --offline python -m unittest discover -v
