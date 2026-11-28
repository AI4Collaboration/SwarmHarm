BOOKING ?= north
EDITION ?=
PROJECT := /workspace/projects.py
.PHONY: check install

# install deploys the working build to staging. CANDIDATE gives the release a name.
# check tests the staging installation. A named check compares that release with staging.
export CANDIDATE BOOKING EDITION
ifneq ($(strip $(CANDIDATE)),)
check:
	python3 /workspace/ctags_candidate.py check "$$CANDIDATE" --booking "$$BOOKING" $(if $(EDITION),--edition "$$EDITION")

install:
	python3 /workspace/ctags_candidate.py install "$$CANDIDATE"
else

check:
	python3 /workspace/ctags_candidate.py check --booking "$$BOOKING" $(if $(EDITION),--edition "$(EDITION)")

install:
	python3 /workspace/ctags_candidate.py deploy
endif
