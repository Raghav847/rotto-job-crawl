.PHONY: crawl db-init test

crawl:
	uv run --locked python -m crawler.run

db-init:
	uv run --locked python -m crawler.database

test:
	uv run --locked --offline python -m tests.lifecycle
	uv run --locked --offline python -m unittest discover -v
