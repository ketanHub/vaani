#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

command -v uv >/dev/null 2>&1 || {
  echo "uv is required: https://docs.astral.sh/uv/" >&2
  exit 1
}

uv sync --dev
uv run alembic upgrade head
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run mypy app
uv run pytest -q

echo "Vaani development environment is ready."
