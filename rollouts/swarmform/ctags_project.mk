BOOKING ?= north
EDITION ?=
PROJECT := /workspace/projects.py
SOURCES := $(wildcard software/*.py)
.PHONY: check install

check:
	python3 $(PROJECT) check-index "$(BOOKING)" $(if $(EDITION),--edition "$(EDITION)")

install:
	@test -n "$(SOURCES)"
	python3 $(PROJECT) commit "$(CURDIR)" $(SOURCES)
