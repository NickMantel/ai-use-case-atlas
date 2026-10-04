.PHONY: install dev test run docker

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

test:
	python -m pytest -q

run:
	uvicorn app.main:app --reload --port 8000

docker:
	docker build -t ai-use-case-atlas .
