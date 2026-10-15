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
  dists/stable/main/binary-aarch64/*.deb
  dists/stable/Release

bootstrap/aarch64/bootstrap-aarch64.zip
bootstrap/aarch64/bootstrap-aarch64.zip.sha256
```

Run `Packages` with the manual input `git openjdk-17` for the initial package
set. The bootstrap workflow defaults to `aarch64` and does not add optional
packages.
