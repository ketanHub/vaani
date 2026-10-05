.PHONY: sync test lint typecheck check dev migrate infra-up infra-down \
	voice-setup voice-setup-gpu voice-dev voice-dev-gpu voice-benchmark \
	voice-load-benchmark telephony-benchmark exotel-benchmark docker-fix

VOICE_AUDIO ?= /tmp/vaani-voice-smoke/english-input.wav
VOICE_MODE ?= wav
VOICE_CONCURRENCY ?= 10

sync:
	uv sync --dev

test:
	uv run pytest -q

lint:
	uv run ruff check app tests migrations
	uv run ruff format --check app tests migrations

typecheck:
	uv run mypy app

check: lint typecheck test

migrate:
	uv run alembic upgrade head

dev:
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8010

voice-setup:
	./scripts/bootstrap_voice.sh

voice-setup-gpu:
	VAANI_VOICE_GPU=1 ./scripts/bootstrap_voice.sh

voice-dev:
	./scripts/dev_voice.sh

voice-dev-gpu:
	./scripts/dev_voice_gpu.sh

voice-benchmark:
	uv run --no-sync python scripts/benchmark_local_voice.py \
		--audio "$(VOICE_AUDIO)" --mode "$(VOICE_MODE)" --turns 3

voice-load-benchmark:
	uv run --no-sync python scripts/benchmark_voice_load.py \
		--audio "$(VOICE_AUDIO)" --concurrency "$(VOICE_CONCURRENCY)"

telephony-benchmark:
	PYTHONPATH=. uv run --no-sync python scripts/benchmark_telephony.py \
		--audio "$(VOICE_AUDIO)" --turns 3

exotel-benchmark:
	PYTHONPATH=. uv run --no-sync python scripts/benchmark_exotel.py \
		--audio "$(VOICE_AUDIO)"

docker-fix:
	./scripts/fix_docker_access.sh

infra-up:
	docker compose up -d --build

infra-down:
	docker compose down
