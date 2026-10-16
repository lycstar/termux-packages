# Sparrow APT repository

Use the flat repository hosted beside the existing GitHub Release deb assets:

```sh
echo 'deb [trusted=yes] https://github.com/lycstar/termux-packages/releases/download/pool ./' > "$PREFIX/etc/apt/sources.list.d/sparrow.list"
apt update
apt install openjdk-17
```

The former GitHub Pages source is retired: APT concatenates the source base URL
with `Filename`, so absolute Release URLs in a Pages index produce invalid URLs.
The flat index uses asset basenames and includes both aarch64 and all packages.

`Repair APT index without rebuilding packages` regenerates metadata from the
existing index, validates asset presence, sizes and available SHA256 digests,
then publishes only Packages, Packages.gz, Packages.xz and Release. It verifies
the published source using real APT and downloads giflib without executing it.
Normal package publishing regenerates the same flat index after uploading debs.
