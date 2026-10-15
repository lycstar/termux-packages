#!/usr/bin/bash

# Emit alternative source locations, not additional source archives. Callers
# must verify every candidate against the recipe's SHA256 before accepting it.
termux_source_mirrors() {
	local url="$1" checksum="$2" path filename base
	[[ "$checksum" =~ ^[[:xdigit:]]{64}$ ]] || return 0
	# Query strings can identify different assets with the same basename.
	[[ "$url" == https://* && "$url" != *\?* && "$url" != *\#* ]] || return 0
	filename="${url##*/}"
	[[ -n "$filename" ]] || return 0

	# Optional private mirror uses content hashes, avoiding filename collisions.
	# This is deliberately separate from R2_PUBLIC_URL (the APT output repo).
	for base in ${TERMUX_SOURCE_MIRRORS:-}; do
		[[ "$base" == https://* ]] || continue
		printf '%s/sha256/%s\n' "${base%/}" "$checksum"
	done

	case "$url" in
		# GitHub release assets intermittently serve HTTP 500 from CI. The
		# proxies forward the original URL verbatim and the downloader still
		# verifies every candidate against the recipe checksum.
		https://github.com/*/releases/download/*)
			printf '%s\n' \
				"https://gh-proxy.com/$url" \
				"https://ghfast.top/$url" \
				"https://ghproxy.net/$url"
			;;
		https://pkgconfig.freedesktop.org/releases/*)
			printf '%s\n' "https://distfiles.macports.org/pkgconfig/$filename"
			if [[ "$filename" == pkg-config-*.tar.gz ]]; then
				printf '%s\n' "https://archive.debian.org/debian/pool/main/p/pkg-config/${filename/pkg-config-/pkg-config_}" | sed 's/\.tar\.gz$/.orig.tar.gz/'
			fi
			;;
		https://ftp.gnu.org/gnu/*|https://ftpmirror.gnu.org/*|https://mirrors.kernel.org/gnu/*)
			path="${url#https://*/}"; path="${path#gnu/}"
			printf '%s\n' "https://mirrors.kernel.org/gnu/$path" \
				"https://ftp.osuosl.org/pub/gnu/$path" "https://ftp.fau.de/gnu/$path"
			;;
		https://www.kernel.org/pub/*|https://cdn.kernel.org/pub/*|https://mirrors.edge.kernel.org/pub/*)
			path="${url#https://*/}"
			printf '%s\n' "https://cdn.kernel.org/$path" "https://mirrors.kernel.org/$path"
			;;
	esac
	# pkgsrc is a broad source archive, including many non-NetBSD projects.
	printf '%s\n' "https://cdn.NetBSD.org/pub/pkgsrc/distfiles/$filename"
}
