# R2 publishing configuration

The workflows publish one aarch64 Sparrow package repository and the bootstrap
archive to one Cloudflare R2 bucket. The package workflow first downloads every
existing `.deb` from R2, adds the current build output, rebuilds the complete
APT metadata, and uploads the result. Later package builds therefore retain all
earlier packages.

Create one bucket named `sparrow-packages` (or another name of your choice) and
make it readable through an R2 custom domain or public `r2.dev` URL. The public
URL must expose objects at its root.

Configure these GitHub Actions repository variables:

| Variable | Example | Purpose |
| --- | --- | --- |
| `R2_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` | S3-compatible endpoint used by Actions to read and write the bucket |
| `R2_BUCKET` | `sparrow-packages` | R2 bucket name |
| `R2_PUBLIC_URL` | `https://packages.example.com` | Public base URL written into `repo.json` and the generated `sources.list` |

Configure these GitHub Actions repository secrets:

| Secret | Purpose |
| --- | --- |
| `R2_ACCESS_KEY_ID` | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret key |

The R2 API token needs object read and write access to the selected bucket. The
public URL and the S3 endpoint are different values: the endpoint is private
storage access for Actions, while the public URL is what Termux uses for APT.

The single bucket is laid out as follows:

```text
apt/termux-main/
  dists/stable/main/binary-aarch64/Packages
  dists/stable/main/binary-aarch64/Packages.xz
  dists/stable/Contents-aarch64
  dists/stable/Contents-aarch64.gz
  dists/stable/main/binary-aarch64/*.deb
  dists/stable/main/binary-all/*.deb
  dists/stable/Release

bootstrap/aarch64/bootstrap-aarch64.zip
bootstrap/aarch64/bootstrap-aarch64.zip.sha256
```

Run `Packages` with the manual input `git openjdk-17` for the initial package
set. The bootstrap workflow defaults to `aarch64` and follows Termux's
`generate-bootstraps.sh`: it reads the published `Packages` index and recursively
downloads the declared runtime dependencies. Build output files that are not in
that dependency closure are never copied into the bootstrap.

The package workflow builds dependencies from source without `-i`/`-I`. R2 is
the publishing destination, not a prerequisite for building: the first build
works with an empty bucket and does not fetch main/root/x11 repository metadata
or GPG signatures from it. Upstream source archives and build tools still need
to be downloaded. Reading old `.deb` objects via the S3 API during publishing is
separate from downloading prebuilt dependencies during compilation.

Set all three variables before starting either build: `R2_PUBLIC_URL` is embedded
in the bootstrap's APT sources. Changing it later requires rebuilding bootstrap
and the `apt` package. Without R2 configuration, workflows only save Actions
artifacts; these use the placeholder URL and are not ready for installation.
Missing credentials produce a warning and leave the Actions artifact available for
download. Bootstrap archives are also copied to the rolling GitHub `pool` release
because the Sparrow app uses that stable download URL; the R2 copy remains useful
as an operator-managed mirror.

Package publishing jobs queue behind one shared lock. Each job downloads old
`.deb` files, merges new files, and regenerates the complete indexes, including
`Architecture: all` entries in the aarch64 index. Package objects are uploaded
first, indexes next, and `Release` last. Old versions are retained, including
when the same package is rebuilt; no remote objects are deleted. If a custom
domain uses Cloudflare caching, bypass caching for APT metadata (`Packages*`,
`Contents*`, and `Release`) to avoid serving stale indexes. The publisher
converts the `Contents-*` files produced by `termux-apt-repo` into the official
Termux layout at `dists/<distribution>/Contents-<arch>.gz`, which is the path
used by `command-not-found`.
