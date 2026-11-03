#!/usr/bin/env bash
# Avoid slow runner mirror selection and bound all package network operations.
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo 'Usage: install-runner-packages.sh PACKAGE ...' >&2
  exit 2
fi

missing=()
for package in "$@"; do
  if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != 'install ok installed' ]]; then
    missing+=("$package")
  fi
done
if [[ ${#missing[@]} -eq 0 ]]; then
  echo 'Required runner packages are already installed; skipping apt.'
  exit 0
fi

# Ubuntu 24.04 uses deb822 .sources; also support legacy .list files.
# Replace mirror-list URIs as well as direct Azure URLs so index requests and
# package downloads both use the official HTTPS archive.
while IFS= read -r -d '' source; do
  sudo sed -i -E \
    -e 's|mirror\+file:/+etc/apt/apt-mirrors.txt|https://archive.ubuntu.com/ubuntu|g' \
    -e 's|mirror\+file:/+etc/apt/apt-mirrors-security.txt|https://security.ubuntu.com/ubuntu|g' \
    -e 's|https?://azure.archive.ubuntu.com/ubuntu|https://archive.ubuntu.com/ubuntu|g' \
    "$source"
done < <(find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -print0)

apt_options=(
  -o Acquire::Retries=2
  -o Acquire::http::Timeout=20
  -o Acquire::https::Timeout=20
)
sudo timeout --kill-after=15s 180s apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
sudo env DEBIAN_FRONTEND=noninteractive timeout --kill-after=15s 300s \
  apt-get "${apt_options[@]}" install -y --no-install-recommends "${missing[@]}"
