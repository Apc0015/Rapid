install:
	python3 -m pip install --upgrade pip
	python3 -m pip install -r requirements.txt

run:
	uvicorn rapid.main:app --reload --host 127.0.0.1 --port 8000

venv:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

.PHONY: install run venv
