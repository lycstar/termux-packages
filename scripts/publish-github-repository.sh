#!/usr/bin/env bash
set -euo pipefail

# GitHub 双出口之二: deb 累积进滚动 Release(pool), 元数据(dists/)发布到
# Release 提供平铺索引。Filename 必须
# 是相对文件名，与 Packages/Release 一起位于同一个 Release 下载目录。
# 需要: GH_TOKEN(github.token, contents:write), GH_REPO; termux-apt-repo 在 PATH。

if [[ $# -ne 1 ]]; then
	echo "Usage: $0 <new-debs-directory>" >&2
	exit 64
fi

: "${GH_REPO:?GH_REPO is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${POOL_TAG:=pool}"
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
# GitHub 资产名不含冒号(上传时静默规范化为点), 本地同步改名以精确对齐已有资产
for f in "$work_dir"/debs/*:*; do
	[[ -f "$f" ]] || continue
	newname=$(basename "$f" | tr ':' '.')
	mv -f "$f" "$(dirname "$f")/$newname"
done
compgen -G "$work_dir/debs/*.deb" > /dev/null || {
	echo "No .deb files found in the pool or current build." >&2
	exit 1
}

# 1) deb 先上传(--clobber 幂等), 使池与资产一致
find "$work_dir/debs" -name '*.deb' -print0 |
	xargs -0 -n 40 gh release upload "$POOL_TAG" -R "$GH_REPO" --clobber

# 2) 重建元数据(本地文件名已规范化为点, 与 GitHub 资产名确定性一致)
termux-apt-repo "$work_dir/debs" "$work_dir/repository" stable main

# 5) finalize: binary-all 归并 + Release 校验清单(基于重写后的最终文件)
python3 "$(dirname "$0")/finalize-r2-repository.py" "$work_dir/repository"

# 6) 平铺索引和 deb 同处 Release 下载目录，apt 不支持 Filename 跨主机 URL。
python3 "$(dirname "$0")/generate-flat-repository.py" "$work_dir/repository" "$work_dir/flat"
gh release upload "$POOL_TAG" -R "$GH_REPO" --clobber \
    "$work_dir/flat/Packages" "$work_dir/flat/Packages.gz" \
    "$work_dir/flat/Packages.xz" "$work_dir/flat/Release"

echo "APT source: deb [trusted=yes] $RELEASE_BASE ./"
