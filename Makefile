# Common tasks. Run `make help` for the list.
PY ?= .venv/bin/python
PYTHON ?= python3
WEB = Code/webapp
ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: help setup seed reindex run test test-ui eval lint package reset docker-up docker-down screenshots

help:            ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup:           ## Create .venv and install everything (Python 3.12 recommended)
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements-dev.txt

seed:            ## Index the sample documents (local mode)
	$(PY) -m advancesearch seed

reindex:         ## Process every document again (text and images) without dropping the index
	$(PY) -m advancesearch reindex --keep-index

run:             ## Start the web app on http://localhost:8000
	cd $(WEB) && ../../$(PY) manage.py runserver 0.0.0.0:8000

test:            ## Core and web app tests
	$(PY) -m pytest Code/core -q
	cd $(WEB) && ../../$(PY) manage.py test

test-ui:         ## Browser tests (needs: .venv/bin/python -m playwright install --with-deps chromium)
	$(PY) -m pytest qa/tests -q

eval:            ## Top-3 accuracy on Data/sample_docs/queries.yaml (after make seed)
	$(PY) -m advancesearch eval

lint:            ## shellcheck, bash -n, JSON validity and Markdown links
	PATH="$(CURDIR)/.venv/bin:$$PATH" shellcheck Deployment/scripts/*.sh
	for f in Deployment/scripts/*.sh; do bash -n $$f; done
	$(PY) qa/check_repo.py

package:         ## Build build/webapp.zip with all libraries included
	PYTHON=$(PY) Deployment/scripts/package.sh --vendor

screenshots:     ## Regenerate the README screenshots (imgs/)
	$(PY) qa/screenshots.py

reset:           ## Delete all local documents, the index and settings overrides
	$(PY) -m advancesearch reset --yes

docker-up:       ## Run the web app with the Azurite storage emulator, with sample documents
	docker compose up --build -d
	docker compose run --rm seed

docker-down:     ## Stop Docker services
	docker compose down
