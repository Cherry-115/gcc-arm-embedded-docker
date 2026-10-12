#!/usr/bin/env bash
set -euo pipefail

if [[ $(uname -s) != Linux || $(uname -m) != aarch64 ]]; then
    echo 'Run this builder on Linux aarch64 (Docker --platform linux/arm64).' >&2
    exit 1
fi
recipe=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
jobs=${JOBS:-$(nproc)}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo 'Invalid JOBS' >&2; exit 1; }
export LC_ALL=C
mkdir -p /downloads /out
# /build is disposable container storage. Refuse to overwrite an existing build.
mkdir /build/toolchain
while read -r checksum filename url; do
    [[ -z $checksum || $checksum == \#* ]] && continue
    if [[ ! -f /downloads/$filename ]]; then
        curl --fail --location --retry 5 --retry-delay 5 --connect-timeout 30 \
            --output "/downloads/$filename.part" "$url"
        mv "/downloads/$filename.part" "/downloads/$filename"
    fi
    (cd /downloads && printf '%s  %s\n' "$checksum" "$filename" | sha256sum --check -)
done < "$recipe/sources.lock"

package=gcc-arm-none-eabi-6-2017-q2-update
archive=$package-aarch64-linux
root=/build/toolchain/$package
tar -xjf "/downloads/$package-src.tar.bz2" -C /build/toolchain
for source in "$root"/src/*.tar.bz2; do
    tar -xf "$source" -C "$root/src"
done
while read -r checksum filename url; do
    [[ -z $checksum || $checksum == \#* || $filename == "$package-src.tar.bz2" ]] && continue
    tar -xf "/downloads/$filename" -C "$root/src"
done < "$recipe/sources.lock"
python3 "$recipe/prepare-sources.py" "$root" "$jobs"
cd "$root"
bash ./build-prerequisites.sh --skip_steps=mingw32 2>&1 | tee /out/prerequisites.log
# Keep GDB independent of the obsolete libtinfo.so.5 / libncurses.so.5 ABI.
# These static archives are found before system shared libraries via upstream's
# -Lbuild-native/host-libs/usr/lib linker flag.
cp /usr/lib/aarch64-linux-gnu/libtinfo.a /usr/lib/aarch64-linux-gnu/libncurses.a \
    build-native/host-libs/usr/lib/
bash ./build-toolchain.sh --skip_steps=mingw32,gdb-with-python,manual 2>&1 | tee /out/toolchain.log

# Test after relocation, so accidental dependencies on the build prefix fail.
mv install-native "/build/$archive"
bash "$recipe/smoke-test.sh" "/build/$archive" 2>&1 | tee /out/smoke-test.log
cp "$recipe/sources.lock" "/build/$archive/share/doc/gcc-arm-none-eabi/"
cp /usr/share/doc/libncurses5/copyright \
    "/build/$archive/share/doc/gcc-arm-none-eabi/ncurses-copyright.txt"
cat > "/build/$archive/share/doc/gcc-arm-none-eabi/build-info.txt" <<EOF
Unofficial Linux aarch64 rebuild of Arm GNU Embedded 6-2017-q2-update.
Host: $(uname -m)-linux-gnu; target: arm-none-eabi; GCC: 6.3.1.
Recipe commit: ${BUILD_COMMIT:-local}
Builder: Ubuntu 18.04, $(gcc --version | head -n 1).
GDB is built without Python. HTML/PDF manuals are not rebuilt.
See the accompanying sources archive for source code and build recipes.
EOF

tar -C /build --owner=0 --group=0 -cJf "/out/$archive.tar.xz" "$archive"
# Include all corresponding upstream sources and the exact build recipe.
mkdir -p /build/release-sources/recipe
while read -r checksum filename url; do
    [[ -z $checksum || $checksum == \#* ]] && continue
    cp "/downloads/$filename" /build/release-sources/
done < "$recipe/sources.lock"
cp "$recipe"/{Dockerfile.build-aarch64,build-aarch64.sh,prepare-sources.py,smoke-test.sh,sources.lock,README-aarch64.md} \
    /build/release-sources/recipe/
tar -C /build --owner=0 --group=0 -cf - release-sources | xz -T "$jobs" -1 > "/out/$archive-sources.tar.xz"
cd /out
sha256sum "$archive.tar.xz" "$archive-sources.tar.xz" > SHA256SUMS
sha256sum --check SHA256SUMS
