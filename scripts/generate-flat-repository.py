#!/usr/bin/env python3
"""Build a flat APT index beside Release assets, without rebuilding any deb."""

import gzip
import hashlib
import json
import lzma
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit


def generate(repository, output, assets_file=None):
    entries = {}
    assets = None
    if assets_file:
        assets = {asset["name"]: asset for asset in json.loads(Path(assets_file).read_text())["assets"]}
    repository = Path(repository)
    indexes = ([repository / "Packages"] if (repository / "Packages").exists()
               else sorted(repository.glob("dists/stable/main/binary-*/Packages")))
    for index in indexes:
        for paragraph in index.read_text().strip().split("\n\n"):
            if not paragraph.strip():
                continue
            fields = dict(line.split(": ", 1) for line in paragraph.splitlines()
                          if ": " in line and not line.startswith((" ", "\t")))
            filename = unquote(urlsplit(fields["Filename"]).path.rsplit("/", 1)[-1])
            if not filename.endswith(".deb") or ":" in filename or filename in (".", ".."):
                raise ValueError(f"Invalid Release asset filename: {filename}")
            if assets is not None:
                asset = assets.get(filename)
                if asset is None or asset["size"] != int(fields["Size"]):
                    raise ValueError(f"Missing or wrong-sized Release asset: {filename}")
                digest = asset.get("digest")
                if digest and digest != "sha256:" + fields["SHA256"]:
                    raise ValueError(f"Release asset checksum mismatch: {filename}")
            paragraph = "\n".join("Filename: " + filename if line.startswith("Filename: ")
                                  else line for line in paragraph.splitlines())
            key = (fields["Package"], fields["Version"], fields["Architecture"])
            if key in entries and entries[key] != paragraph:
                raise ValueError(f"Conflicting package metadata: {key}")
            entries[key] = paragraph
    if not entries:
        raise ValueError("No package entries found")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payload = ("\n\n".join(entries[key] for key in sorted(entries)) + "\n\n").encode()
    files = {"Packages": payload, "Packages.gz": gzip.compress(payload, mtime=0),
             "Packages.xz": lzma.compress(payload)}
    architectures = sorted({key[2] for key in entries})
    release = ["Origin: Sparrow", "Label: Sparrow toolchain packages",
               "Date: " + format_datetime(datetime.now(timezone.utc), usegmt=True),
               "Architectures: " + " ".join(architectures), "Description: Sparrow flat APT repository"]
    for algorithm, label in (("sha256", "SHA256"), ("sha512", "SHA512")):
        release.append(label + ":")
        for name, data in files.items():
            release.append(f" {hashlib.new(algorithm, data).hexdigest()} {len(data)} {name}")
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / "Release").write_text("\n".join(release) + "\n")
    print(f"Generated flat index: {len(entries)} package versions; architectures: {architectures}")


if __name__ == "__main__":
    generate(*sys.argv[1:])
