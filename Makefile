# Optional shortcuts for people who have make. The pipeline itself is one
# command and needs no make:  python -m pipeline <command>
# Run it with the project's own Python, for example on Windows:
#   .venv\Scripts\python -m pipeline film
PYTHON ?= $(shell command -v python 2>/dev/null || command -v python3)

.PHONY: help install validate-draft validate doctor smoke narration keyframes radio film

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

install: ## install the Python dependencies
	$(PYTHON) -m pip install -r requirements.txt

validate-draft: ## check the storyboard's structure while it still has TODOs
	$(PYTHON) -m pipeline validate --allow-draft

validate: ## check the finished storyboard
	$(PYTHON) -m pipeline validate

doctor: ## check tools, keys (names only) and the storyboard
	$(PYTHON) -m pipeline doctor

smoke: ## call each hosted model once and log it
	$(PYTHON) -m pipeline smoke

narration: ## generate the narration line for every shot
	$(PYTHON) -m pipeline narration

keyframes: ## generate the reference sheet and the still for every shot
	$(PYTHON) -m pipeline keyframes

radio: ## narration over a placeholder score, on a black screen
	$(PYTHON) -m pipeline radio

film: ## everything: narration, keyframes and the edit, in both aspect ratios
	$(PYTHON) -m pipeline film
