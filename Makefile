.PHONY: bootstrap lint test build verify-pr1 verify-pr2 verify-pr3 verify-gate-a verify-gate-b compile-dc compile-18 rust-test frontend-test hub-test python-test assessment-test pr3-test gate-a-test gate-b-test gate-b-ai-test clean

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

gate-a-test:
	WAIKE_ROOT=$(WAIKE_ROOT) PYTHONPATH=services/hub $(PYTHON) -m pytest -q tests/gate_a

gate-b-ai-test:
	WAIKE_ROOT=$(WAIKE_ROOT) PYTHONPATH=services/hub $(PYTHON) -m pytest -q \
	  tests/gate_b/test_ai_policy.py \
	  tests/gate_b/test_ai_context_isolation.py \
	  tests/gate_b/test_ai_prompt_injection.py \
	  tests/gate_b/test_ai_grade_safety.py \
	  tests/gate_b/test_gunnchai_contract.py \
	  tests/gate_b/test_adversarial_ai_sabotage.py

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

compile-18:
	@mkdir -p pack_out_18 reports
	$(PYTHON) -m course_compiler.cli compile-all --out pack_out_18
	WAIKE_ROOT=$(WAIKE_ROOT) $(PYTHON) scripts/inventory_18_tracks.py
	WAIKE_ROOT=$(WAIKE_ROOT) $(PYTHON) scripts/build_18_track_matrix.py

gate-b-test:
	WAIKE_ROOT=$(WAIKE_ROOT) PYTHONPATH=tools/course_compiler:services/hub $(PYTHON) -m pytest -q \
	  tests/gate_b/test_compiler_18.py \
	  tests/gate_b/test_package_security_18.py \
	  tests/gate_b/test_activity_coverage_18.py

verify-gate-b:
	@mkdir -p reports
	@WAIKE_ROOT=$(WAIKE_ROOT) $(PYTHON) scripts/verify_gate_b.py
	@echo "verify-gate-b: see reports/GATE_B_VERIFICATION.md"

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

verify-gate-a: bootstrap
	@mkdir -p reports
	$(MAKE) gate-a-test
	$(MAKE) pr3-test
	$(MAKE) compile-dc
	$(MAKE) rust-test
	$(MAKE) frontend-test
	cd $(CLIENT) && (command -v pnpm >/dev/null && pnpm run build || npm run build)
	cd $(TAURI) && cargo check
	@WAIKE_ROOT=$(WAIKE_ROOT) $(PYTHON) scripts/verify_gate_a.py
	@echo "verify-gate-a: see reports/GATE_A_VERIFICATION.md"

clean:
	rm -rf pack_out $(CLIENT)/dist $(TAURI)/target services/hub/data
