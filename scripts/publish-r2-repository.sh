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
	--exclude '*' --include '*.deb' \
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
python3 "$(dirname "$0")/finalize-r2-repository.py" "$work_dir/repository"

# command-not-found's generate-db.js fetches dists/stable/Contents-<arch>.gz
# (no component, gzip) while termux-apt-repo writes
# dists/stable/main/Contents-<arch>[.xz]. Publish translated copies; they are
# unreferenced by the Release file, so apt clients ignore them.
for contents in "$work_dir"/repository/dists/stable/main/Contents-*; do
	[[ -f "$contents" ]] || continue
	arch="${contents##*/Contents-}"
	arch="${arch%.xz}"
	case "$contents" in
		*.xz) xz -dc "$contents" ;;
		*)    cat "$contents" ;;
	esac | gzip -n > "$work_dir/repository/dists/stable/Contents-${arch}.gz"
done

# Publish package objects before the indexes that reference them. Retain old
# versions so clients holding an older index can still download those files.
aws s3 sync "$work_dir/repository" "$remote_uri" \
	--exclude '*' --include '*.deb' \
	--endpoint-url "$R2_ENDPOINT" --region auto
aws s3 sync "$work_dir/repository" "$remote_uri" \
	--exclude '*.deb' --exclude 'dists/stable/Release' \
	--endpoint-url "$R2_ENDPOINT" --region auto
aws s3 cp "$work_dir/repository/dists/stable/Release" "$remote_uri/dists/stable/Release" \
	--endpoint-url "$R2_ENDPOINT" --region auto \
	--cache-control 'no-cache, max-age=0, must-revalidate'

echo "Published cumulative APT repository to $remote_uri"
