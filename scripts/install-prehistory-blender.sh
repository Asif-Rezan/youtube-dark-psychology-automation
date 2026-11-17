#!/usr/bin/env bash
set -euo pipefail

version=4.5.16
archive="blender-$version-linux-x64.tar.xz"
sha256=23432b064977908beb1ab4b7f32f024e7331105c875c187dce002aff84b10c11
install_dir="$RUNNER_TEMP/prehistory-blender"

check_version() {
  local binary="$1" output
  [[ -x "$binary" ]] || return 1
  output=$("$binary" --version) || return 1
  [[ "${output%%$'\n'*}" == "Blender $version"* ]] || return 1
  printf '%s\n' "${output%%$'\n'*}"
}

if check_version "$install_dir/blender"; then
  echo 'Reusing cached headless Blender'
else
  scratch=$(mktemp -d "$RUNNER_TEMP/prehistory-blender.XXXXXX")
  trap 'rm -rf -- "$scratch"' EXIT
  mirrors=(
    https://mirror.blender.org/release
    https://download.blender.org/release
    https://mirrors.dotsrc.org/blender/blender-release
    https://ftp.nluug.nl/graphics/blender/release
    https://mirrors.ocf.berkeley.edu/blender/release
  )
  verified=false
  for mirror in "${mirrors[@]}"; do
    echo "Downloading Blender $version from $mirror"
    if curl --fail --silent --show-error --location --retry 2 --retry-max-time 90 \
        --connect-timeout 15 --max-time 240 \
        "$mirror/Blender4.5/$archive" -o "$scratch/$archive" &&
        (cd "$scratch" && printf '%s  %s\n' "$sha256" "$archive" | sha256sum --check); then
      verified=true
      break
    fi
    echo "::warning::Blender download or checksum failed at $mirror"
  done
  if [[ "$verified" != true ]]; then
    echo "::error::Could not obtain the verified Blender $version archive from any configured mirror"
    exit 1
  fi
  mkdir "$scratch/extracted"
  tar -xf "$scratch/$archive" --strip-components=1 -C "$scratch/extracted"
  check_version "$scratch/extracted/blender"
  if [[ -e "$install_dir" ]]; then
    mv "$install_dir" "$scratch/old"
  fi
  mv "$scratch/extracted" "$install_dir"
fi

printf 'PREHISTORY_BLENDER=%s/blender\n' "$install_dir" >> "$GITHUB_ENV"
