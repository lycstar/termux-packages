#!/usr/bin/env bash
set -euo pipefail
base="${1:?Release base URL is required}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/lists/partial" "$work/cache/archives/partial"
echo "deb [trusted=yes arch=aarch64] $base ./" > "$work/sources.list"
options=(
  -o "Dir::Etc::sourcelist=$work/sources.list"
  -o 'Dir::Etc::sourceparts=-'
  -o "Dir::State::lists=$work/lists"
  -o "Dir::Cache=$work/cache"
  -o 'APT::Architecture=aarch64'
  -o 'APT::Architectures::=aarch64'
  -o 'APT::Sandbox::User=root'
  -o 'APT::Update::Error-Mode=any'
)
apt-get "${options[@]}" update
cd "$work"
apt-get "${options[@]}" download giflib:aarch64
test -s giflib_*_aarch64.deb
echo 'Real APT update and package download passed.'
