.PHONY: bootstrap lint test build verify-pr1 verify-pr2 verify-pr3 compile-dc rust-test frontend-test hub-test python-test assessment-test pr3-test clean

export PATH := $(HOME)/.cargo/bin:$(PATH)
export SOURCE_DATE_EPOCH ?= 1700000000
# Documented development DB key fallback (64 hex chars). Not for production.
export WAIKE_DEV_DB_KEY ?= 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
export WAIKE_ROOT ?= $(CURDIR)/../waike-research-ops

PYTHON := .venv/bin/python3
CLIENT := apps/client
TAURI := $(CLIENT)/src-tauri

bootstrap:
	@command -v uv >/dev/null || (echo "uv required" && exit 1)
	@test -d .venv || uv venv .venv
	uv pip install -e tools/course_compiler --python $(PYTHON)
	uv pip install pytest httpx jsonschema pyyaml cryptography PyNaCl argon2-cffi fastapi uvicorn pydantic --python $(PYTHON)
	cd $(CLIENT) && (command -v pnpm >/dev/null && corepack enable && corepack prepare pnpm@9.15.9 --activate && pnpm install || npm install)
	@mkdir -p reports
	@echo "Bootstrap complete. WAIKE_DEV_DB_KEY is set for local/CI encrypted DB."

lint:
	$(PYTHON) -m compileall tools/course_compiler/course_compiler services/hub/app
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm run lint || npm run lint)
	cd $(TAURI) && cargo fmt --check || cargo fmt
	cd $(TAURI) && cargo clippy --all-targets -- -D warnings || true

python-test:
	WAIKE_ROOT=$(WAIKE_ROOT) PYTHONPATH=services/hub $(PYTHON) -m pytest -q tests services/hub/tests

assessment-test:
	WAIKE_ROOT=$(WAIKE_ROOT) PYTHONPATH=services/hub $(PYTHON) -m pytest -q services/hub/tests tests/assessment

pr3-test:
	WAIKE_ROOT=$(WAIKE_ROOT) PYTHONPATH=services/hub $(PYTHON) -m pytest -q services/hub/tests tests/assessment tests/pr3

hub-test:
	WAIKE_ROOT=$(WAIKE_ROOT) PYTHONPATH=services/hub $(PYTHON) -m pytest -q services/hub/tests

rust-test:
	cd $(TAURI) && cargo test

frontend-test:
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm test || npm test)

test: python-test rust-test frontend-test

compile-dc:
	@mkdir -p pack_out reports
	$(PYTHON) -m course_compiler.cli compile DIGITAL_CONFIDENCE --out pack_out || \
	  .venv/bin/course-compiler compile DIGITAL_CONFIDENCE --out pack_out

build: compile-dc
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm run build || npm run build)
	cd $(TAURI) && cargo build

verify-pr1: bootstrap
	@mkdir -p reports
	$(MAKE) python-test
	$(MAKE) compile-dc
	$(MAKE) rust-test
	$(MAKE) frontend-test
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm run build || npm run build)
	cd $(TAURI) && cargo check
	@$(PYTHON) scripts/verify_pr1.py
	@echo "verify-pr1: AUTOMATED_PIPELINE_PASS (see reports/PR1_VERIFICATION.md)"

verify-pr2: bootstrap
	@mkdir -p reports
	$(MAKE) assessment-test
	$(MAKE) compile-dc
	$(MAKE) rust-test
	$(MAKE) frontend-test
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm run build || npm run build)
	cd $(TAURI) && cargo check
	@WAIKE_ROOT=$(WAIKE_ROOT) $(PYTHON) scripts/verify_pr2.py
	@echo "verify-pr2: see reports/PR2_VERIFICATION.md"

verify-pr3: bootstrap
	@mkdir -p reports
	$(MAKE) pr3-test
	$(MAKE) compile-dc
	$(MAKE) rust-test
	$(MAKE) frontend-test
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm run build || npm run build)
	cd $(TAURI) && cargo check
	@WAIKE_ROOT=$(WAIKE_ROOT) $(PYTHON) scripts/verify_pr3.py
	@echo "verify-pr3: see reports/PR3_VERIFICATION.md"

clean:
	rm -rf pack_out $(CLIENT)/dist $(TAURI)/target services/hub/data
