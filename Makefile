.PHONY: help run demo test smoke check
PYTHON ?= python3

help:            ## Show available targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ —/'

run:             ## Start the office in live mode (needs HERMES_API_KEY)
	$(PYTHON) -m hermes_office

demo:            ## Start the office with synthetic fixtures (no secrets)
	$(PYTHON) -m hermes_office --demo

test:            ## Run the unit test suite
	$(PYTHON) -m pytest tests

smoke:           ## Boot the demo server and exercise it over HTTP
	$(PYTHON) scripts/smoke.py

check: test smoke  ## Everything CI runs
