PYTHON = python3
VENV = venv

.PHONY: all venv install run run-launcher quick-start clean

all: venv install

venv:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r config/requirements.txt

install:
	$(VENV)/bin/pip install -e .

run:
	$(VENV)/bin/python main.py

run-launcher:
	./bin/sudoers.sh

quick-start:
	./bin/launch.sh

clean:
	rm -rf $(VENV) __pycache__ *.egg-info build dist lib/core/__pycache__
