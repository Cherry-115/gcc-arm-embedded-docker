#!/usr/bin/env python3
"""Adapt Arm's archived build scripts for a native Linux aarch64 build."""
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1])
jobs = int(sys.argv[2])
if jobs < 1:
    raise SystemExit('JOBS must be positive')
common = root / 'build-common.sh'
text = common.read_text()

def replace_once(old, new):
    global text
    if text.count(old) != 1:
        raise SystemExit('Unexpected upstream script: ' + old)
    text = text.replace(old, new, 1)

# Upstream derives the release name from today's date and clears environment vars.
replace_once('RELEASEDATE=`date +%Y%m%d`', 'RELEASEDATE=20170620')
replace_once('JOBS=`grep ^processor /proc/cpuinfo|wc -l`', 'JOBS=' + str(jobs))
replace_once('PACKAGE_NAME_SUFFIX=linux', 'PACKAGE_NAME_SUFFIX=aarch64-linux')
common.write_text(text)

# libelf's 2009 config scripts predate aarch64. Use the copies shipped with GCC.
for package in root.joinpath('src').iterdir():
    if package.is_dir() and package.name != 'gcc':
        for name in ('config.guess', 'config.sub'):
            for path in package.rglob(name):
                shutil.copy2(root / 'src/gcc' / name, path)

# We publish the original, checksum-verified source archives alongside the
# recipe, so skip upstream's expensive source repackaging (which also expects
# a regenerated PDF even with --skip_steps=manual).
script = root / 'build-toolchain.sh'
text = script.read_text()
marker = 'echo Task [V-0] /package_sources/'
if text.count(marker) != 1:
    raise SystemExit('Unexpected upstream source packaging step')
script.write_text(text.split(marker)[0] + '\n# Sources are packaged by build-aarch64.sh.\n')
