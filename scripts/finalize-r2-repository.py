#!/usr/bin/env python3
"""Include architecture-independent packages and refresh unsigned APT metadata."""

import gzip
import hashlib
import lzma
from pathlib import Path
import sys


def finalize(repository):
    distribution = Path(repository) / "dists/stable"
    component = distribution / "main"
    # termux-apt-repo writes Contents-* under the component directory and
    # creates only .xz files. command-not-found follows the official Termux
    # layout and requests gzipped indexes at the distribution root.
    for contents in list(component.glob("Contents-*")):
        if contents.suffix == ".xz":
            contents.unlink()
            continue
        if contents.suffix == ".gz":
            continue
        target = distribution / contents.name
        target.write_bytes(contents.read_bytes())
        contents.unlink()
        gzip_path = target.with_name(target.name + ".gz")
        with gzip.GzipFile(gzip_path, "wb", compresslevel=9, mtime=0) as compressed:
            compressed.write(target.read_bytes())
        xz_path = target.with_name(target.name + ".xz")
        if xz_path.exists():
            xz_path.unlink()
    all_index = component / "binary-all/Packages"
    if all_index.exists():
        independent = all_index.read_bytes().rstrip() + b"\n\n"
        native_index = component / "binary-aarch64/Packages"
        if not native_index.exists():
            native_index.parent.mkdir(parents=True, exist_ok=True)
            native_index.write_bytes(b"")
        for index in component.glob("binary-*/Packages"):
            if index != all_index:
                content = index.read_bytes().rstrip()
                content = (content + b"\n\n" if content else b"") + independent
                index.write_bytes(content)
                index.with_suffix(".xz").write_bytes(lzma.compress(content))

    release = distribution / "Release"
    # Retain descriptive fields but replace every checksum section, since the
    # architecture indexes above have changed. Codename must match sources.list.
    fields = []
    for line in release.read_text().splitlines():
        if line.startswith("MD5Sum:"):
            break
        if line.startswith("Architectures:") and "aarch64" not in line.split()[1:]:
            line += " aarch64"
        fields.append("Codename: stable" if line.startswith("Codename:") else line)
    metadata = sorted(
        path for path in distribution.rglob("*")
        if path.is_file() and not path.name.endswith(".deb") and path != release
    )
    for algorithm, label in (("md5", "MD5Sum"), ("sha1", "SHA1"),
                             ("sha256", "SHA256"), ("sha512", "SHA512")):
        fields.append(label + ":")
        for path in metadata:
            data = path.read_bytes()
            digest = hashlib.new(algorithm, data).hexdigest()
            fields.append(f" {digest} {len(data)} {path.relative_to(distribution)}")
    release.write_text("\n".join(fields) + "\n")


if __name__ == "__main__":
    finalize(sys.argv[1])
