BOOKING ?= north
EDITION ?=
PROJECT := /workspace/projects.py
.PHONY: check install

check:
	@set -eu; d=$$(mktemp -d); trap 'rm -r "$$d"' EXIT; \
	  entry="$(CURDIR)/software/pandoc.py"; \
	  if ! test -f "$$entry"; then 	    python3 $(PROJECT) checkout "$$d/converter" software/; entry="$$d/converter/software/pandoc.py"; \
	  fi; \
	  set --; if test -n "$(EDITION)"; then set -- --proof-edition "$(EDITION)"; fi; \
	  python3 /workspace/field_reader.py "$(BOOKING)" --checkout-kit "$$d/kit" "$$@" --proof-converter "$$entry"

install:
	@test -f software/pandoc.py
	find software -type d \( -name __pycache__ -o -name .git \) -prune -o -type f ! -name '*.pyc' ! -name '*.pyo' -exec python3 $(PROJECT) commit "$(CURDIR)" {} +
