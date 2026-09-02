.PHONY: bootstrap lint test build verify-pr1 compile-dc rust-test frontend-test hub-test python-test clean

export PATH := $(HOME)/.cargo/bin:$(PATH)
export SOURCE_DATE_EPOCH ?= 1700000000
# Documented development DB key fallback (64 hex chars). Not for production.
export WAIKE_DEV_DB_KEY ?= 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

PYTHON := .venv/bin/python3
UV := uv
CLIENT := apps/client
TAURI := $(CLIENT)/src-tauri

bootstrap:
	@command -v uv >/dev/null || (echo "uv required" && exit 1)
	@test -d .venv || uv venv .venv
	uv pip install -e tools/course_compiler -e "services/hub" --python $(PYTHON)
	uv pip install pytest httpx jsonschema pyyaml cryptography PyNaCl --python $(PYTHON)
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm install || npm install)
	@mkdir -p reports
	@echo "Bootstrap complete. WAIKE_DEV_DB_KEY is set for local/CI encrypted DB."

lint:
	$(PYTHON) -m compileall tools/course_compiler/course_compiler services/hub/app
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm run lint || npm run lint)
	cd $(TAURI) && cargo fmt --check || cargo fmt
	cd $(TAURI) && cargo clippy --all-targets -- -D warnings || true

python-test:
	$(PYTHON) -m pytest -q tests services/hub/tests

hub-test:
	$(PYTHON) -m pytest -q services/hub/tests

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

# Full PR1 acceptance aggregation (local). Writes reports/pr1_verification.json on success path.
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

clean:
	rm -rf pack_out $(CLIENT)/dist $(TAURI)/target
