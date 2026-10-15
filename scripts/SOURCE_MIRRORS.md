# Source download mirrors and cache

All callers of `termux_download` share the same source fallback logic. This
covers package archives and build tools that use this helper, in both the
Packages and bootstrap workflows. Git clones, pip and Cargo have their own
fetchers and are not changed here.

| Original source | Alternative locations |
| --- | --- |
| pkg-config on freedesktop.org | MacPorts distfiles, Debian archive, NetBSD pkgsrc distfiles |
| Xorg on freedesktop.org | NetBSD pkgsrc distfiles |
| GNU archives | kernel.org, OSUOSL, FAU, NetBSD pkgsrc distfiles |
| Linux kernel archives | kernel.org CDN and mirror, NetBSD pkgsrc distfiles |
| Other HTTPS archives, including GNOME | Original URL, then NetBSD pkgsrc distfiles |

The distfile archives are broad collections, not complete copies of every
upstream. A missing version, network failure, or SHA256 mismatch advances to
the next candidate. freedesktop.org downloads try the mirrors first because
those hosts repeatedly failed during the initial builds. Other downloads try
the upstream first. No TLS validation or checksum validation is disabled.

Only a recipe with a SHA256 can use mirrors and the shared cache. A download
without a checksum, or a URL with a query/fragment, retains its original URL.
`TERMUX_PKG_SRCURL` arrays still mean multiple required archives, not mirrors.
Do not add mirror URLs to those arrays.

`TERMUX_SOURCE_CACHE_DIR` enables a shared content-addressed directory. Files
are stored as `<directory>/<sha256>` only after verification. Every cache hit
is verified again. The two Actions workflows restore this directory into the
workspace, pass its mounted path into Docker, and save verified downloads even
if a later build stage fails. Only archives are shared, not compiled packages,
installed prefixes, or architecture-specific build state.

For a private mirror, set `TERMUX_SOURCE_MIRRORS` inside the build container to
space-separated HTTPS base URLs. Each mirror must serve exact original bytes
at `<base>/sha256/<recipe-sha256>`. No upload happens automatically. This is
independent of `R2_PUBLIC_URL`, which remains the output APT repository URL.

Run the offline regression tests with:

```sh
python3 -m unittest discover -s scripts/tests -p 'test_source_download.py' -v
```
