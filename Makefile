.PHONY: lint fmt test

lint:
	ruff check src/ tests/

fmt:
	black src/ tests/
	ruff check src/ tests/ --fix

test:
	pytest --tb=short
