# GNU Arm Embedded 6-2017-q2-update for Linux aarch64

This builds **GCC 6.3.1** from Arm's original `6-2017-q2-update` source release.
The toolchain runs on **Linux aarch64 (arm64)** and produces **arm-none-eabi**
bare-metal ARM code. It does not produce AArch64 Linux applications.

## GitHub Actions and Releases

Workflow: `.github/workflows/gcc-6-2017-q2-aarch64.yml`.

- Pull requests changing this directory or the workflow build and test only.
- Matching changes pushed to `master` build, test, and automatically publish a
  release tagged `6-2017-q2-update-aarch64-r<RUN_NUMBER>`.
- Pushing a tag named `6-2017-q2-update-aarch64-*` also builds and publishes
  under that exact tag. Do not reuse tags for different commits.
- **Actions → GCC 6-2017-q2 Linux aarch64 → Run workflow** supports manual
  builds. Select `master` and check `publish` to publish; the default is build only.
- Release publication uses the workflow's `GITHUB_TOKEN` with `contents: write`.
  No personal access token or repository secret is required. GitHub Actions
  must be enabled and repository/organization policy must allow that permission.
- Published assets are never replaced by rerunning a workflow. An interrupted
  draft publication is resumed. Trigger a new run for a new release.

Assets:

- `gcc-arm-none-eabi-6-2017-q2-update-aarch64-linux.tar.xz`: binaries and libraries.
- `gcc-arm-none-eabi-6-2017-q2-update-aarch64-linux-sources.tar.xz`: original
  source archives, dependency sources, checksum lockfile, and exact build recipe.
- `SHA256SUMS`: checksums for both archives.

Build logs and release files are also retained as Actions artifacts for 14 days.
The complete source build can take a long time; the job limit is 330 minutes.
Only downloaded source archives are cached, and their hashes are rechecked on
all runs, including cache hits.

## Install

Download the binary archive and `SHA256SUMS` from this repository's Releases:

```sh
# Check the downloaded binary (the source archive is optional for installation).
grep '  gcc-arm-none-eabi-6-2017-q2-update-aarch64-linux.tar.xz$' SHA256SUMS | sha256sum -c -
tar -xJf gcc-arm-none-eabi-6-2017-q2-update-aarch64-linux.tar.xz
export PATH="$PWD/gcc-arm-none-eabi-6-2017-q2-update-aarch64-linux/bin:$PATH"
arm-none-eabi-gcc --version
```

The builder uses Ubuntu 18.04 (GCC 7, glibc 2.27) for compatibility with these
2017 sources. Releases are tested inside that container and again on the native
Ubuntu 24.04 ARM64 Actions runner. GDB's terminal libraries are linked statically
so it does not require the old `libtinfo.so.5`/`libncurses.so.5` packages.

Included: binutils, C/C++, upstream `rmprofile` multilibs, newlib, newlib-nano,
normal/nano libstdc++, and GDB. Python-enabled GDB and regenerated HTML/PDF
manuals are omitted. Upstream release notes, licenses, and samples are retained.
These are community rebuilds, not official Arm binary releases.

The existing `Dockerfile` downloads the upstream x86 binary and is unchanged.
Use `Dockerfile.build-aarch64` for this source build.

## Local reproduction

Requires Docker on Linux arm64, or Docker Desktop on Apple Silicon. Run from the
repository root. The long build runs in disposable container storage; downloads
and outputs are kept on the host.

```sh
mkdir -p downloads dist
docker build --platform linux/arm64 \
  -f 6-2017-q2-update/Dockerfile.build-aarch64 \
  -t gcc-arm-builder 6-2017-q2-update
docker run --rm --platform linux/arm64 \
  --mount "type=bind,src=$PWD/downloads,dst=/downloads" \
  --mount "type=bind,src=$PWD/dist,dst=/out" \
  -e JOBS=4 -e BUILD_COMMIT="$(git rev-parse HEAD)" gcc-arm-builder
```

Use at least 4 CPUs, 8 GB memory, and approximately 20 GB free disk space.
On Linux, output files can be owned by root because the build runs in a container.
The source bundle contains all archives from `sources.lock`; mount them as
`/downloads` to rebuild without downloading sources again (building the builder
image still needs Ubuntu packages).

`prepare-sources.py` pins the release label/date, limits build parallelism,
refreshes pre-AArch64 `config.guess`/`config.sub` from the bundled GCC source,
and replaces upstream's redundant source repackaging with the source bundle.
It leaves GCC, binutils, newlib and GDB source code unchanged.

Smoke tests check native ELF AArch64 executables, GCC version/target, relocated
installation, GDB startup, C/C++ linking with LTO for Cortex-M0/M3/M4 hard float,
and normal/nano libraries for every multilib. Tests compile ARM binaries but do
not run firmware on physical target hardware.
