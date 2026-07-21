.DEFAULT_GOAL := test

EXAMPLES_DIR := examples/server
CLIENTTEST_PY := examples/clienttest_py
CLIENTTEST_TS := examples/clienttest_ts
BACKOFFICE := examples/backoffice
MANAGE := cd $(EXAMPLES_DIR) && python manage.py
DJANGO_SETTINGS_MODULE := articles_project.settings

.PHONY: generate_py generate_ts generate migrate runserver docs docs_serve
.PHONY: test_lib test_sdk_py test_sdk_ts test_all test
.PHONY: backoffice install lint typecheck clean

# ── SDK generation ──────────────────────────────────────────────────────────

generate_py:
	rm -rf $(CLIENTTEST_PY)/articles_sdk
	$(MANAGE) generate_jsonapi_client \
	    articles_app.views::api \
	    --language python \
	    --output $(CURDIR)/$(CLIENTTEST_PY)/articles_sdk

generate_ts:
	rm -rf $(CLIENTTEST_TS)/articles_sdk
	$(MANAGE) generate_jsonapi_client \
	    articles_app.views::api \
	    --language typescript \
	    --output $(CURDIR)/$(CLIENTTEST_TS)/articles_sdk
	rm -rf $(BACKOFFICE)/src/articles_sdk
	cp -r $(CLIENTTEST_TS)/articles_sdk $(BACKOFFICE)/src/articles_sdk
	find $(BACKOFFICE)/src/articles_sdk -name '*.ts' -exec sh -c \
	    "echo '// @ts-nocheck' | cat - '{}' > /tmp/tsfix && mv /tmp/tsfix '{}'" \;

generate: generate_py generate_ts

# ── Server ──────────────────────────────────────────────────────────────────

migrate:
	$(MANAGE) migrate

runserver:
	$(MANAGE) runserver

# ── Backoffice ──────────────────────────────────────────────────────────────

backoffice:
	cd $(BACKOFFICE) && npm run dev

# ── Docs ────────────────────────────────────────────────────────────────────

docs:
	uv run mkdocs build

docs_serve:
	uv run mkdocs serve

# ── Tests ───────────────────────────────────────────────────────────────────

test_lib:
	uv run pytest tests/server/

test_sdk_py:
	uv run pytest tests/client/

test_sdk_ts:
	cd src/djsonapi_client_ts && npx vitest run

test_all: test_lib test_sdk_py test_sdk_ts

test: test_all

# ── Utility ──────────────────────────────────────────────────────────────────

install:
	uv sync

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

typecheck:
	uv run pyright

clean:
	rm -rf site/
