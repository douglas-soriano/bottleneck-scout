.PHONY: help install run test

PORT ?= 3006
PYTHON ?= python3
VENV := .venv

install:
	$(PYTHON) -m venv $(VENV)
	pip install -r requirements.txt

run:
	uvicorn app:app --host 127.0.0.1 --port $(PORT)

test:
	pytest
