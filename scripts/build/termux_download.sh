#!/usr/bin/bash

# Resolve from this file so the helper works both sourced and standalone.
. "$(dirname "${BASH_SOURCE[0]}")/termux_source_mirrors.sh"

termux_download() {
	if [[ $# != 2 ]] && [[ $# != 3 ]]; then
		echo "termux_download(): Invalid arguments - expected <URL> <DESTINATION> [<CHECKSUM>]" 1>&2
		return 1
	fi
	local URL="$1"
	local DESTINATION="$2"
	local CHECKSUM="${3:-SKIP_CHECKSUM}"

	if [[ "$URL" =~ ^file://(/[^/]+)+$ ]]; then
		local source="${URL:7}" # Remove `file://` prefix

		if [ -d "$source" ]; then
			# Create tar file from local directory
			echo "Downloading local source directory at '$source'"
			rm -f "$DESTINATION"
			(cd "$(dirname "$source")" && tar -cf "$DESTINATION" --exclude=".git" "$(basename "$source")")
			return 0
		elif [ ! -f "$source" ]; then
			echo "No local source file found at path of URL '$URL'"
			return 1
		else
			ln -sf "$source" "$DESTINATION"
			return 0
		fi
	fi

	if [ -f "$DESTINATION" ] && [ "$CHECKSUM" != "SKIP_CHECKSUM" ]; then
		# Keep existing file if checksum matches.
		local EXISTING_CHECKSUM
		EXISTING_CHECKSUM=$(sha256sum "$DESTINATION" | cut -d' ' -f1)
		[[ "$EXISTING_CHECKSUM" == "$CHECKSUM" ]] && return
	fi

	local cache_file="" actual_checksum candidate tmpfile
	local -a candidates=() mirrors=()
	if [[ "$CHECKSUM" =~ ^[[:xdigit:]]{64}$ ]]; then
		if [[ -n "${TERMUX_SOURCE_CACHE_DIR:-}" ]]; then
			cache_file="$TERMUX_SOURCE_CACHE_DIR/$CHECKSUM"
			if [[ -f "$cache_file" ]]; then
				actual_checksum=$(sha256sum "$cache_file" | cut -d' ' -f1)
				if [[ "$actual_checksum" == "$CHECKSUM" ]]; then
					echo "Using verified source cache for $URL"
					cp "$cache_file" "$DESTINATION" || return 1
					return 0
				fi
				echo "Ignoring corrupt source cache: $cache_file" >&2
			fi
		fi
		while IFS= read -r candidate; do
			[[ -n "$candidate" ]] && mirrors+=("$candidate")
		done < <(termux_source_mirrors "$URL" "$CHECKSUM")
	fi

	# These hosts repeatedly time out in CI. Try independent mirrors first.
	candidates=("$URL")
	if [[ -n "${mirrors[0]:-}" ]]; then
		case "$URL" in
			https://pkgconfig.freedesktop.org/*|https://xorg.freedesktop.org/*)
				candidates=("${mirrors[@]}" "$URL") ;;
			*) candidates=("$URL" "${mirrors[@]}") ;;
		esac
	fi
	local -a curl_options=(
		--fail --location
		--retry 2 --retry-connrefused --retry-delay 2
		--connect-timeout 20 --retry-max-time 60
		--speed-limit 1000 --speed-time 60
	)
	[[ "${TERMUX_QUIET_BUILD:-}" == true ]] && curl_options+=(--no-progress-meter)
	tmpfile=$(mktemp "$TERMUX_PKG_TMPDIR/download.${TERMUX_PKG_NAME-unnamed}.XXXXXXXXX") || return 1
	local seen=$'\n'
	for candidate in "${candidates[@]}"; do
		# Keep duplicate aliases from multiplying retry time.
		[[ "$seen" == *$'\n'"$candidate"$'\n'* ]] && continue
		seen+="$candidate"$'\n'
		echo "Downloading $candidate"
		if ! curl "${curl_options[@]}" --output "$tmpfile" "$candidate"; then
			echo "Source unavailable; trying next location: $candidate" >&2
			continue
		fi
		actual_checksum=$(sha256sum "$tmpfile" | cut -d' ' -f1)
		if [[ -n "$CHECKSUM" && "$CHECKSUM" != SKIP_CHECKSUM && "$CHECKSUM" != "$actual_checksum" ]]; then
			printf 'Wrong checksum for %s\nExpected: %s\nActual:   %s\n' \
				"$candidate" "$CHECKSUM" "$actual_checksum" >&2
			continue
		fi
		if [[ -z "$CHECKSUM" ]]; then
			printf 'WARNING: No checksum check for %s:\nActual: %s\n' "$candidate" "$actual_checksum"
		fi
		# Only verified archives enter the shared cache. A failed build can still
		# save successful downloads, without caching partial or untrusted files.
		if [[ -n "$cache_file" ]]; then
			local cache_tmp
			if mkdir -p "$TERMUX_SOURCE_CACHE_DIR" && cache_tmp=$(mktemp "$TERMUX_SOURCE_CACHE_DIR/.download.XXXXXXXXX"); then
				if cp "$tmpfile" "$cache_tmp"; then
					mv "$cache_tmp" "$cache_file" || rm -f "$cache_tmp"
				else
					rm -f "$cache_tmp"
				fi
			fi
		fi
		if ! mv "$tmpfile" "$DESTINATION"; then
			rm -f "$tmpfile"
			return 1
		fi
		return 0
	done
	rm -f "$tmpfile"
	echo "Failed to download $URL from all source locations" >&2
	return 1
}

# Make script standalone executable as well as sourceable
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
	termux_download "$@"
fi
