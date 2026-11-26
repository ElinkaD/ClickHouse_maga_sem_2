.PHONY: run rund services schema gen load setup teardown test stop clean
.DEFAULT_GOAL = run
ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif

# Runs all services in detached mode.
run:
	docker compose --env-file .env.local up -d --build

# Runs all services without detached mode (for debugging).
rund:
	docker compose --env-file .env.local up --build

# Shows all service statuses.
services:
	docker compose --env-file .env.local ps

# Creates the database and applies DDL from sql/ddl/.
schema:
	$(PYTHON) -m app.admin schema

gen:
	$(PYTHON) -m app.generate

load:
	$(PYTHON) -m app.admin load

setup:
	$(MAKE) schema
	$(MAKE) gen
	$(MAKE) load

teardown:
	$(PYTHON) -m app.admin teardown

test:
	$(PYTHON) -m unittest discover -s tests -v

# Stops all running services.
stop:
	docker compose --env-file .env.local down

# Removes containers; bind-mounted data in volume/ remains on disk.
clean:
	docker compose --env-file .env.local down -v
