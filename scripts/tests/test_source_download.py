#!/usr/bin/env python3
"""Exercise downloader fallbacks without relying on any public mirror."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts/build/termux_download.sh'
GOOD = b'verified source archive\n'
SHA = hashlib.sha256(GOOD).hexdigest()
URL = 'https://pkgconfig.freedesktop.org/releases/pkg-config-0.29.2.tar.gz'
MAC = 'https://distfiles.macports.org/pkgconfig/pkg-config-0.29.2.tar.gz'
NET = 'https://cdn.NetBSD.org/pub/pkgsrc/distfiles/pkg-config-0.29.2.tar.gz'


class SourceDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.dest = self.root / 'archive'
        self.cache = self.root / 'cache'
        self.responses = self.root / 'responses.json'
        self.calls = self.root / 'calls'
        curl = self.bin / 'curl'
        curl.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]; url=args[-1]
with open(os.environ['TEST_CALLS'], 'a') as f: f.write(url+'\\n')
response=json.loads(Path(os.environ['TEST_RESPONSES']).read_text()).get(url)
if response is None: sys.exit(22)
if isinstance(response,int): sys.exit(response)
Path(args[args.index('--output')+1]).write_text(response)
''')
        curl.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'TERMUX_PKG_TMPDIR': str(self.root),
                    'TERMUX_SOURCE_CACHE_DIR': str(self.cache),
                    'TERMUX_SOURCE_MIRRORS': '',
                    'TEST_RESPONSES': str(self.responses), 'TEST_CALLS': str(self.calls)}

    def download(self, responses, checksum=SHA, url=URL):
        self.responses.write_text(json.dumps(responses))
        return subprocess.run(['bash', '-eu', '-c',
                               'source "$1"; termux_download "$2" "$3" "$4"',
                               'test', str(HELPER), url, str(self.dest), checksum],
                              env=self.env, capture_output=True, text=True)

    def test_network_failure_switches_to_independent_mirror(self):
        result = self.download({MAC: 35, NET: GOOD.decode()})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.dest.read_bytes(), GOOD)
        self.assertEqual((self.cache / SHA).read_bytes(), GOOD)

    def test_wrong_checksum_switches_mirror(self):
        result = self.download({MAC: 'wrong contents', NET: GOOD.decode()})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Wrong checksum', result.stderr)
        self.assertEqual(self.dest.read_bytes(), GOOD)

    def test_cache_reuse_does_not_need_network(self):
        self.assertEqual(self.download({MAC: GOOD.decode()}).returncode, 0)
        self.dest.unlink()
        count = self.calls.read_text()
        result = self.download({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), count)
        self.assertEqual(self.dest.read_bytes(), GOOD)

    def test_corrupt_cache_is_replaced(self):
        self.cache.mkdir()
        (self.cache / SHA).write_text('corrupt')
        result = self.download({MAC: GOOD.decode()})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.cache / SHA).read_bytes(), GOOD)

    def test_failed_download_preserves_destination_and_cleans_tempfiles(self):
        self.dest.write_text('original')
        result = self.download({MAC: 'bad', NET: 'also bad', URL: 'bad upstream'})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.dest.read_text(), 'original')
        self.assertFalse(list(self.root.glob('download.*')))
        self.assertFalse((self.cache / SHA).exists())

    def test_unverified_download_uses_only_original_and_is_not_cached(self):
        result = self.download({URL: 'unverified'}, checksum='SKIP_CHECKSUM')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [URL])
        self.assertFalse(self.cache.exists())

    def test_query_url_is_not_rewritten(self):
        url = URL + '?version=2'
        result = self.download({url: GOOD.decode()}, url=url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [url])

    def test_private_hash_mirror(self):
        self.env['TERMUX_SOURCE_MIRRORS'] = 'https://sources.example.test https://backup.example.test/'
        result = self.download({'https://backup.example.test/sha256/' + SHA: GOOD.decode()})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines()[:2], [
            'https://sources.example.test/sha256/' + SHA,
            'https://backup.example.test/sha256/' + SHA])

    def test_gnu_mirror_path_and_duplicate_elimination(self):
        url = 'https://mirrors.kernel.org/gnu/bash/bash-5.3.tar.gz'
        alternative = 'https://ftp.osuosl.org/pub/gnu/bash/bash-5.3.tar.gz'
        result = self.download({alternative: GOOD.decode()}, url=url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [url, alternative])

    def test_xorg_uses_broad_distfile_mirror_before_failing_upstream(self):
        url = 'https://xorg.freedesktop.org/releases/individual/lib/libXScrnSaver-1.2.5.tar.xz'
        alternative = 'https://cdn.NetBSD.org/pub/pkgsrc/distfiles/libXScrnSaver-1.2.5.tar.xz'
        result = self.download({alternative: GOOD.decode()}, url=url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [alternative])

    def test_local_source_still_works(self):
        source = self.root / 'local'
        source.write_bytes(GOOD)
        result = self.download({}, url=source.as_uri())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.dest.read_bytes(), GOOD)
        self.assertFalse(self.calls.exists())


if __name__ == '__main__':
    unittest.main()
