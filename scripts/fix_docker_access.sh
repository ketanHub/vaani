#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed." >&2
  exit 1
fi

sudo groupadd -f docker
sudo usermod -aG docker "$USER"

if snap list docker >/dev/null 2>&1; then
  sudo snap restart docker
elif systemctl list-unit-files docker.service >/dev/null 2>&1; then
  sudo systemctl restart docker
fi

echo
echo "Docker group access configured for $USER."
echo "Either sign out and back in, or run:"
echo "  newgrp docker"
echo
echo "Then verify with:"
echo "  docker info"
