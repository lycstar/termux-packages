#!/usr/bin/env bash
set -euo pipefail

# GitHub 双出口之二: deb 累积进滚动 Release(pool), 元数据(dists/)发布到
# gh-pages。Filename 以绝对 URL 指向 release 资产, apt 原生支持。
# 需要: GH_TOKEN(github.token, contents:write), GH_REPO; termux-apt-repo 在 PATH。

if [[ $# -ne 1 ]]; then
	echo "Usage: $0 <new-debs-directory>" >&2
	exit 64
fi

: "${GH_REPO:?GH_REPO is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${POOL_TAG:=pool}"
: "${PAGES_BRANCH:=gh-pages}"
RELEASE_BASE="https://github.com/${GH_REPO}/releases/download/${POOL_TAG}"

new_debs_dir="$(realpath "$1")"
[[ -d "$new_debs_dir" ]] || { echo "Package directory not found: $new_debs_dir" >&2; exit 1; }

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
mkdir -p "$work_dir/debs" "$work_dir/repository"

# 滚动池: 拉取 release 里全部旧 deb, 与新 deb 合并后整体重建索引
gh release download "$POOL_TAG" -R "$GH_REPO" -D "$work_dir/debs" -p '*.deb' 2>/dev/null \
	|| echo "Pool release has no assets yet; starting fresh."
find "$new_debs_dir" -type f -name '*.deb' -exec cp -f {} "$work_dir/debs/" \;
compgen -G "$work_dir/debs/*.deb" > /dev/null || {
	echo "No .deb files found in the pool or current build." >&2
	exit 1
}

# 1) 重建元数据(与 R2 管线同款生成器)
termux-apt-repo "$work_dir/debs" "$work_dir/repository" stable main

# 2) Filename 重写为 release 资产绝对 URL, 压缩变体同步再生
python3 - "$work_dir/repository" "$RELEASE_BASE" <<'PY'
import lzma
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1])
base = sys.argv[2].rstrip('/')
for packages in repo.rglob('Packages'):
    text = packages.read_text()
    rewritten = re.sub(
        r'(?m)^(Filename: ).*/([^/]+)$',
        lambda m: m.group(1) + base + '/' + m.group(2),
        text,
    )
    packages.write_text(rewritten)
    sibling = packages.with_suffix('.xz')
    if sibling.exists():
        sibling.write_bytes(lzma.compress(rewritten))
    gz = packages.with_suffix('.gz')
    if gz.exists():
        import gzip
        gz.write_bytes(gzip.compress(rewritten))
PY

# 3) finalize: binary-all 归并 + Release 校验清单(基于重写后的最终文件)
python3 "$(dirname "$0")/finalize-r2-repository.py" "$work_dir/repository"

# 4) deb 上传进滚动池(--clobber 幂等, 同名覆盖)
find "$work_dir/debs" -name '*.deb' -print0 |
	xargs -0 -n 40 gh release upload "$POOL_TAG" -R "$GH_REPO" --clobber

# 5) 元数据推到 gh-pages
git clone --depth 1 --branch "$PAGES_BRANCH" \
	"https://x-access-token:${GH_TOKEN}@github.com/${GH_REPO}.git" \
	"$work_dir/pages" 2>/dev/null || {
	git init -b "$PAGES_BRANCH" "$work_dir/pages"
	git -C "$work_dir/pages" remote add origin \
		"https://x-access-token:${GH_TOKEN}@github.com/${GH_REPO}.git"
}
mkdir -p "$work_dir/pages/dists"
cp -a "$work_dir/repository/dists/." "$work_dir/pages/dists/"
git -C "$work_dir/pages" add -A
git -C "$work_dir/pages" -c user.name=sparrow-ci -c user.email=ci@lycstar.cc \
	commit -m "apt metadata $(date -u '+%Y-%m-%dT%H:%M:%SZ')" || echo "metadata unchanged"
git -C "$work_dir/pages" push origin "HEAD:$PAGES_BRANCH"

echo "Published cumulative APT repository to GitHub (${RELEASE_BASE}, Pages: dists/)"
