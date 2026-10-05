#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This helper is for Ubuntu/Linux only." >&2
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required for Docker system installation." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker

echo
echo "Docker installed. To use Docker without sudo, run:"
echo "  sudo usermod -aG docker $USER"
echo "Then sign out and sign back in before running docker compose."
