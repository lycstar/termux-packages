import gzip
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "flat", Path(__file__).resolve().parents[1] / "generate-flat-repository.py")
flat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flat)


class FlatRepositoryTests(unittest.TestCase):
    def test_relative_assets_deduplication_compression_and_release_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paragraph = ("Package: test\nVersion: 1\nArchitecture: all\n"
                         "Filename: https://github.com/org/repo/releases/download/pool/test_1_all.deb\n"
                         "Size: 4\nSHA256: " + hashlib.sha256(b"test").hexdigest() + "\n\n")
            for arch in ("all", "aarch64"):
                index = root / f"dists/stable/main/binary-{arch}/Packages"
                index.parent.mkdir(parents=True)
                index.write_text(paragraph)
            assets = root / "assets.json"
            assets.write_text(json.dumps({"assets": [{"name": "test_1_all.deb", "size": 4,
                "digest": "sha256:" + hashlib.sha256(b"test").hexdigest()}]}))
            flat.generate(root, root / "out", assets)
            payload = (root / "out/Packages").read_bytes()
            self.assertEqual(payload.count(b"Package: test"), 1)
            self.assertIn(b"Filename: test_1_all.deb\n", payload)
            self.assertNotIn(b"https://", payload)
            self.assertEqual(gzip.decompress((root / "out/Packages.gz").read_bytes()), payload)
            self.assertEqual(lzma.decompress((root / "out/Packages.xz").read_bytes()), payload)
            self.assertIn(hashlib.sha256(payload).hexdigest(), (root / "out/Release").read_text())
            assets.write_text('{"assets": []}')
            with self.assertRaisesRegex(ValueError, "Missing"):
                flat.generate(root, root / "out", assets)
            assets.write_text(json.dumps({"assets": [{"name": "test_1_all.deb", "size": 4,
                                                       "digest": "sha256:wrong"}]}))
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                flat.generate(root, root / "out", assets)


if __name__ == "__main__":
    unittest.main()
