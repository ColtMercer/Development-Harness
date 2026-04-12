.PHONY: install dev lint typecheck test serve clean init

install:
	pip install -e .

dev:
	pip install -e ".[all,dev]"

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

typecheck:
	mypy src/devharness/

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=devharness --cov-report=html

serve:
	harness serve

init:
	harness init

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
