.PHONY: install run test eval data build

install:
	pip install -r requirements.txt

run:
	cd backend && uvicorn app.main:app --reload --port 8000

test:
	pytest

eval:
	python scripts/run_evaluation.py

data:
	python scripts/generate_dataset.py

build:
	python scripts/build_standalone.py
