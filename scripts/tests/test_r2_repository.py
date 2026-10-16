"""Exercise cumulative publishing with real debs and a local S3 stand-in.

Run: python3 -m unittest discover -s scripts/tests -p 'test_r2_repository.py'
Requires termux-apt-repo==0.5, ar, tar, and xz.
"""

import hashlib
import gzip
import io
import json
import lzma
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class FinalizeIndexTests(unittest.TestCase):
    def test_contents_is_published_at_distribution_root_as_gzip(self):
        with tempfile.TemporaryDirectory(prefix="sparrow-finalize-") as temp:
            repository = Path(temp) / "dists/stable/main"
            repository.mkdir(parents=True)
            (repository / "Contents-aarch64").write_text("usr/bin/demo demo\n")
            (repository / "Contents-aarch64.xz").write_bytes(b"stale")
            release = repository.parent / "Release"
            release.write_text(
                "Codename: termux\nArchitectures: aarch64\nMD5Sum:\n"
            )
            subprocess.run(
                ["python3", str(ROOT / "scripts/finalize-r2-repository.py"), temp],
                check=True,
            )
            root_contents = repository.parent / "Contents-aarch64"
            root_gzip = repository.parent / "Contents-aarch64.gz"
            self.assertEqual(root_contents.read_text(), "usr/bin/demo demo\n")
            with gzip.open(root_gzip, "rt") as compressed:
                self.assertEqual(compressed.read(), root_contents.read_text())
            self.assertFalse((repository / "Contents-aarch64").exists())
            self.assertFalse((repository / "Contents-aarch64.xz").exists())
            self.assertIn("Contents-aarch64.gz", release.read_text())


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sparrow-r2-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.remote = self.work / "remote"
        self.remote.mkdir()
        self.incoming = self.work / "incoming"
        self.incoming.mkdir()
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.log = self.work / "calls.jsonl"
        aws = self.bin / "aws"
        aws.write_text('''#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_AWS_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if os.environ.get("FAIL_REMOTE_READ") and args[2].startswith("s3://"):
    sys.exit(1)
def local(path):
    return Path(os.environ["FAKE_R2"]) if path.startswith("s3://") else Path(path)
source, target = local(args[2]), local(args[3])
if args[1] == "cp":
    target = Path(os.environ["FAKE_R2"]) / "dists/stable/Release"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
else:
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if "--include" in args and path.suffix != ".deb":
            continue
        if "--include" not in args and (path.suffix == ".deb" or str(relative) == "dists/stable/Release"):
            continue
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
''')
        aws.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        AWS_ACCESS_KEY_ID="test", AWS_SECRET_ACCESS_KEY="test",
                        R2_ENDPOINT="https://r2.invalid", R2_BUCKET="test",
                        FAKE_R2=str(self.remote), FAKE_AWS_LOG=str(self.log))

    def deb(self, name, arch="aarch64", version="1.0"):
        path = self.incoming / f"{name}_{version}_{arch}.deb"
        with tempfile.TemporaryDirectory(dir=self.work) as build:
            build = Path(build)
            (build / "debian-binary").write_text("2.0\n")
            for filename, mode, member, data in (
                ("control.tar.gz", "w:gz", "./control",
                 f"Package: {name}\nVersion: {version}\nArchitecture: {arch}\nDescription: Test\n".encode()),
                ("data.tar.xz", "w:xz", f"./usr/share/{name}", b"test\n"),
            ):
                with tarfile.open(build / filename, mode) as archive:
                    info = tarfile.TarInfo(member)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            # Write the portable SysV ar format used by Debian, including on
            # macOS where the system ar defaults to Mach-O archives.
            with path.open("wb") as archive:
                archive.write(b"!<arch>\n")
                for member in ("debian-binary", "control.tar.gz", "data.tar.xz"):
                    data = (build / member).read_bytes()
                    header = f"{member + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
                    archive.write(header.encode())
                    archive.write(data)
                    if len(data) % 2:
                        archive.write(b"\n")
        return path

    def publish(self, **environment):
        return subprocess.run(["bash", str(ROOT / "scripts/publish-r2-repository.sh"),
                               str(self.incoming)], env=dict(self.env, **environment),
                              capture_output=True, text=True)

    def test_later_package_retains_old_packages_and_all_architecture(self):
        self.deb("git")
        self.deb("ca-certificates", "all")
        first = self.publish()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        for path in self.incoming.iterdir():
            path.unlink()
        self.deb("openssh")
        self.deb("git", version="2.0")
        second = self.publish()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        dist = self.remote / "dists/stable"
        index = dist / "main/binary-aarch64/Packages"
        entries = index.read_text().strip().split("\n\n")
        self.assertEqual(len(entries), 4)
        self.assertEqual(lzma.decompress(index.with_suffix(".xz").read_bytes()), index.read_bytes())
        for entry in entries:
            fields = dict(line.split(": ", 1) for line in entry.splitlines())
            data = (self.remote / fields["Filename"]).read_bytes()
            self.assertEqual(int(fields["Size"]), len(data))
            self.assertEqual(fields["SHA256"], hashlib.sha256(data).hexdigest())
        release = (dist / "Release").read_text()
        self.assertIn("Codename: stable\n", release)
        sha256 = release.split("SHA256:\n")[1].split("SHA512:\n")[0]
        for line in sha256.splitlines():
            digest, size, filename = line.split()
            data = (dist / filename).read_bytes()
            self.assertEqual(int(size), len(data))
            self.assertEqual(digest, hashlib.sha256(data).hexdigest())
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(len(calls), 8)
        for start in (0, 4):
            self.assertTrue(calls[start][2].startswith("s3://"))
            self.assertIn("--include", calls[start + 1])
            self.assertIn("--exclude", calls[start + 2])
            self.assertEqual(calls[start + 3][1], "cp")
        self.assertFalse(any("--delete" in call for call in calls))

    def test_remote_read_failure_does_not_publish(self):
        self.deb("openssh")
        result = self.publish(FAIL_REMOTE_READ="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.log.read_text().splitlines()), 1)
        self.assertEqual(list(self.remote.iterdir()), [])

    def test_only_architecture_independent_packages_are_visible_on_aarch64(self):
        self.deb("ca-certificates", "all")
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        distribution = self.remote / "dists/stable"
        self.assertIn("Package: ca-certificates\n",
                      (distribution / "main/binary-aarch64/Packages").read_text())
        release = (distribution / "Release").read_text()
        architectures = release.split("Architectures: ")[1].splitlines()[0]
        self.assertIn("aarch64", architectures.split())


if __name__ == "__main__":
    unittest.main()
