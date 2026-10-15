#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
	echo "Usage: $0 <new-debs-directory>" >&2
	exit 64
fi

: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is required}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is required}"
: "${R2_ENDPOINT:?R2_ENDPOINT is required}"
: "${R2_BUCKET:?R2_BUCKET is required}"
: "${R2_APT_PREFIX:=apt/termux-main}"

new_debs_dir="$(realpath "$1")"
[[ -d "$new_debs_dir" ]] || { echo "Package directory not found: $new_debs_dir" >&2; exit 1; }

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
mkdir -p "$work_dir/remote" "$work_dir/debs" "$work_dir/repository"

remote_uri="s3://${R2_BUCKET}/${R2_APT_PREFIX}"
aws s3 sync "$remote_uri" "$work_dir/remote" \
	--endpoint-url "$R2_ENDPOINT" --region auto

# The published repository is the durable package store. Rebuild metadata from
# all retained debs so a run for a new package cannot remove older packages.
find "$work_dir/remote" -type f -name '*.deb' -exec cp -f {} "$work_dir/debs/" \;
find "$new_debs_dir" -type f -name '*.deb' -exec cp -f {} "$work_dir/debs/" \;

compgen -G "$work_dir/debs/*.deb" > /dev/null || {
	echo "No .deb files found in the existing repository or current build." >&2
	exit 1
}

termux-apt-repo "$work_dir/debs" "$work_dir/repository" stable main

aws s3 sync "$work_dir/repository" "$remote_uri" \
	--endpoint-url "$R2_ENDPOINT" --region auto --delete

echo "Published cumulative APT repository to $remote_uri"
