# GNU Arm Embedded 6-2017-q2-update for Linux aarch64

This builds **GCC 6.3.1** from Arm's original `6-2017-q2-update` source release.
The toolchain runs on **Linux aarch64 (arm64)** and produces **arm-none-eabi**
bare-metal ARM code. It does not produce AArch64 Linux applications.

## GitHub Actions and Releases

Workflow: `.github/workflows/gcc-6-2017-q2-aarch64.yml`.

- The workflow runs **only by manual dispatch**. Pushes, pull requests and tags
  do not start builds.
- **Actions → GCC 6-2017-q2 Linux aarch64 → Run workflow** starts a build.
  Select `master` and check `publish` to publish after all tests pass; the default
  is build only. Releases use `6-2017-q2-update-aarch64-r<RUN_NUMBER>` tags.
  GitHub must have this workflow on the default branch before the manual Run
  workflow button is available.
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

Completed binary/source archives and `SHA256SUMS` are packaged before smoke
tests and uploaded as the `gcc-6-aarch64-release-<RUN_ATTEMPT>` Actions artifact
before the runner test, with 30-day retention. They remain downloadable when either the
container or runner smoke test fails. Failed tests still fail the job and block
Release publication; artifacts from failed runs are unverified diagnostic builds.
Build and smoke-test logs are retained for 14 days as
`gcc-6-aarch64-logs-<RUN_ATTEMPT>`, including the runner test output in
`runner-smoke-test.log`. Attempt-specific names keep earlier packages and logs
available and prevent duplicate-name failures on reruns. Release publication
downloads the exact artifact ID from the successful build job, so rerunning
only the release job also reuses the correct package.
A build failing before packaging has logs but may have no complete archives.
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
so it does not require the old `libtinfo.so.5`/`libncurses.so.5` packages. The
builder combines ncurses and terminfo objects into `libcurses.a`, matching GDB's
`-lcurses` configure result. Smoke tests reject shared terminal-library
dependencies before starting GDB, even when the builder has those libraries.

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

Fast pipeline regression checks (Python 3, GCC and GNU binutils; no ARM build):

```sh
python3 -m unittest discover -s 6-2017-q2-update/tests -v
```
