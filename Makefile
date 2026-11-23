.PHONY: install test init dashboard doctor roi clean

VENV := .venv
PY := $(VENV)/bin/python
CORTICAL := $(VENV)/bin/cortical

install:
	@chmod +x install.sh
	@./install.sh

test:
	@PYTHONPATH=src $(PY) -m unittest tests/test_cortical.py -q

init:
	@$(CORTICAL) init --yes

dashboard:
	@$(CORTICAL) cortical --serve --open

doctor:
	@$(CORTICAL) doctor

roi:
	@$(CORTICAL) roi

clean:
	@rm -rf build dist src/*.egg-info .pytest_cache
	@find src tests -type d -name __pycache__ -exec rm -rf {} +
