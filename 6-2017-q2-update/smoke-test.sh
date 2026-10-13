#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
prefix=$(cd -- "${1:?Usage: smoke-test.sh TOOLCHAIN_DIRECTORY}" && pwd)
export PATH="$prefix/bin:$PATH"
[[ $(uname -s) == Linux && $(uname -m) == aarch64 ]]
[[ $(arm-none-eabi-gcc -dumpmachine) == arm-none-eabi ]]
[[ $(arm-none-eabi-gcc -dumpversion) == 6.3.1 ]]
arm-none-eabi-gcc --version
arm-none-eabi-g++ --version
# GCC's driver, compiler backends, linker, debugger and LTO backend must all
# be native AArch64 executables, not downloaded x86 binaries.
for binary in "$prefix"/bin/arm-none-eabi-{gcc,g++,as,ld,gdb} \
    "$prefix"/lib/gcc/arm-none-eabi/6.3.1/{cc1,cc1plus,lto1}; do
    file "$binary"
    readelf -h "$binary" | grep -E 'Machine:.*AArch64'
    dependencies=$(readelf -d "$binary")
    printf '%s\n' "$dependencies" | grep NEEDED || true
    if [[ $dependencies =~ lib(tinfo|ncurses|curses)[^]]*\.so ]]; then
        echo "Unexpected shared terminal library dependency: $binary" >&2
        exit 1
    fi
done
arm-none-eabi-gdb --batch -ex 'show version'
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
cat > "$scratch/test.c" <<'EOF'
#include <stdio.h>
int main(void) { return puts("arm-none-eabi C smoke test") < 0; }
EOF
cat > "$scratch/test.cpp" <<'EOF'
#include <vector>
#include <numeric>
int main() {
    std::vector<int> values{1, 2, 3};
    return std::accumulate(values.begin(), values.end(), 0) != 6;
}
EOF
for cpu in cortex-m0 cortex-m3 cortex-m4; do
    flags=(-mthumb -mcpu="$cpu")
    if [[ $cpu == cortex-m4 ]]; then
        flags+=(-mfpu=fpv4-sp-d16 -mfloat-abi=hard)
    fi
    for variant in normal nano; do
        specs=(--specs=nosys.specs)
        [[ $variant == normal ]] || specs+=(--specs=nano.specs)
        for lang in c cpp; do
            compiler=arm-none-eabi-gcc
            [[ $lang == c ]] || compiler=arm-none-eabi-g++
            output="$scratch/$cpu-$variant-$lang.elf"
            "$compiler" "${flags[@]}" "${specs[@]}" -Os -flto \
                "$scratch/test.$lang" -o "$output"
            arm-none-eabi-readelf -h "$output" | grep -E 'Machine:.*ARM$'
            arm-none-eabi-size "$output"
        done
    done
done
# Check that nano libraries exist for every shipped multilib variant.
while IFS=';' read -r directory _options; do
    for library in libc.a libc_nano.a libstdc++.a libstdc++_nano.a; do
        test -s "$prefix/arm-none-eabi/lib/$directory/$library"
    done
done < <(arm-none-eabi-gcc -print-multi-lib)
echo 'aarch64 host / ARM target smoke tests passed.'
