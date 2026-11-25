PYTHON ?= python3

.PHONY: install validate-draft validate

install:
	$(PYTHON) -m pip install -r requirements.txt

validate-draft:
	$(PYTHON) pipeline/validate_storyboard.py --allow-draft

validate:
	$(PYTHON) pipeline/validate_storyboard.py
