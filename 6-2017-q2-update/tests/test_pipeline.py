"""Exercise linking and failure recovery without the hour-long ARM build."""
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

RECIPE = Path(__file__).resolve().parents[1]
BUILD = (RECIPE / 'build-aarch64.sh').read_text()
ARCHIVE = 'gcc-arm-none-eabi-6-2017-q2-update-aarch64-linux'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


@unittest.skipUnless(all(shutil.which(x) for x in ('gcc', 'ar', 'readelf', 'xz')),
                     'requires GCC and GNU binutils/xz')
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.libs = self.root / 'system'
        self.libs.mkdir()
        for name, code in (
            ('ncurses', 'extern int tgetent(void); int waddstr(void) { return tgetent(); }'),
            ('tinfo', 'int tgetent(void) { return 0; }'),
        ):
            source = self.libs / (name + '.c')
            source.write_text(code)
            obj = self.libs / (name + '.o')
            run('gcc', '-fPIC', '-c', str(source), '-o', str(obj))
            run('ar', 'rcs', str(self.libs / ('lib' + name + '.a')), str(obj))

    def merge_curses(self, cwd):
        # Execute the exact MRI archive recipe used by the builder.
        script = BUILD.split('ar -M <<EOF\n', 1)[1].split('\nEOF', 1)[0]
        script = script.replace('/usr/lib/aarch64-linux-gnu', str(self.libs))
        run('ar', '-M', input=script + '\n', cwd=cwd)

    def test_curses_name_uses_static_ncurses_and_terminfo(self):
        host = self.root / 'build-native/host-libs/usr/lib'
        host.mkdir(parents=True)
        main = self.root / 'main.c'
        main.write_text('extern int waddstr(void); int main(void) { return waddstr(); }')
        # Model Ubuntu's shared libcurses name. Merely staging libncurses.a
        # and libtinfo.a does not affect the actual -lcurses lookup.
        run('gcc', '-shared', str(self.libs / 'ncurses.o'), str(self.libs / 'tinfo.o'),
            '-Wl,-soname,libncurses.so.5', '-o', str(self.libs / 'libncurses.so.5'))
        (self.libs / 'libcurses.so').symlink_to('libncurses.so.5')
        for name in ('ncurses', 'tinfo'):
            shutil.copy(self.libs / ('lib' + name + '.a'), host)
        binary = self.root / 'probe'
        link = ('gcc', str(main), '-L' + str(host), '-L' + str(self.libs),
                '-lcurses', '-o', str(binary))
        run(*link)
        self.assertIn('libncurses.so.5', run('readelf', '-d', str(binary)).stdout)
        self.merge_curses(self.root)
        run(*link)
        self.assertNotIn('libncurses.so.5', run('readelf', '-d', str(binary)).stdout)
        (self.libs / 'libncurses.so.5').unlink()
        run(str(binary))  # Both curses and terminfo resolve without the old .so.

    def test_smoke_failure_preserves_packages_and_exit_status(self):
        recipe = self.root / 'recipe'
        shutil.copytree(RECIPE, recipe, ignore=shutil.ignore_patterns('tests', '__pycache__'))
        downloads, out, build = [self.root / name for name in ('downloads', 'out', 'build')]
        downloads.mkdir()
        build.mkdir()
        package = 'gcc-arm-none-eabi-6-2017-q2-update'
        upstream = self.root / package
        (upstream / 'src').mkdir(parents=True)
        with tarfile.open(upstream / 'src/fixture.tar.bz2', 'w:bz2') as archive:
            archive.add(self.libs / 'tinfo.c', arcname='fixture/tinfo.c')
        (upstream / 'build-prerequisites.sh').write_text('mkdir -p build-native/host-libs/usr/lib\n')
        (upstream / 'build-toolchain.sh').write_text(
            'mkdir -p install-native/share/doc/gcc-arm-none-eabi\n'
            'echo compiled-toolchain > install-native/compiler\n')
        source = downloads / (package + '-src.tar.bz2')
        with tarfile.open(source, 'w:bz2') as archive:
            archive.add(upstream, arcname=package)
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        (recipe / 'sources.lock').write_text(f'{checksum} {source.name} https://unused.invalid/source\n')
        (recipe / 'prepare-sources.py').write_text('# Fixture needs no source adaptations.\n')
        (recipe / 'smoke-test.sh').write_text('echo deliberate-smoke-failure\nexit 23\n')
        copyright_file = self.root / 'copyright'
        copyright_file.write_text('fixture license\n')
        script = re.sub(r'/build(?=[/\s"])', str(build), BUILD)
        script = script.replace('/downloads', str(downloads))
        script = script.replace('/out', str(out))
        script = script.replace('/usr/lib/aarch64-linux-gnu', str(self.libs))
        script = script.replace('/usr/share/doc/libncurses5/copyright', str(copyright_file))
        (recipe / 'build-aarch64.sh').write_text(script)
        # Only the host architecture is mocked; tar, ar, xz, tee, hashing and
        # the full packaging/error propagation logic run normally.
        mocks = self.root / 'mocks'
        mocks.mkdir()
        (mocks / 'uname').write_text('#!/bin/sh\ncase "$1" in -m) echo aarch64;; *) echo Linux;; esac\n')
        (mocks / 'uname').chmod(0o755)
        env = dict(os.environ, PATH=str(mocks) + ':' + os.environ['PATH'], JOBS='1')
        result = subprocess.run(['bash', str(recipe / 'build-aarch64.sh')], env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        run('sha256sum', '--check', 'SHA256SUMS', cwd=out)
        for suffix in ('.tar.xz', '-sources.tar.xz'):
            with tarfile.open(out / (ARCHIVE + suffix)) as archive:
                self.assertTrue(archive.getnames())
        self.assertIn('deliberate-smoke-failure', (out / 'smoke-test.log').read_text())

    def test_smoke_rejects_shared_terminal_abi_before_gdb_startup(self):
        prefix = self.root / 'toolchain'
        binaries = prefix / 'bin'
        binaries.mkdir(parents=True)
        mocks = self.root / 'mocks'
        mocks.mkdir()
        scripts = {
            mocks / 'uname': 'case "$1" in -m) echo aarch64;; *) echo Linux;; esac',
            mocks / 'file': 'echo native-fixture',
            mocks / 'readelf': (
                'if [ "$1" = -h ]; then echo "Machine: AArch64"; '
                'elif [ "${2##*/}" = arm-none-eabi-gdb ]; then '
                'echo "0x00000001 (NEEDED) Shared library: [libtinfo.so.5]"; fi'),
            binaries / 'arm-none-eabi-gcc': (
                'case "$1" in -dumpmachine) echo arm-none-eabi;; '
                '-dumpversion) echo 6.3.1;; *) echo fixture;; esac'),
            binaries / 'arm-none-eabi-g++': 'echo fixture',
            binaries / 'arm-none-eabi-gdb': 'echo should-not-start >&2; exit 127',
        }
        for path, content in scripts.items():
            path.write_text('#!/bin/sh\n' + content + '\n')
            path.chmod(0o755)
        env = dict(os.environ, PATH=str(mocks) + ':' + os.environ['PATH'])
        result = subprocess.run(['bash', str(RECIPE / 'smoke-test.sh'), str(prefix)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('Unexpected shared terminal library dependency', result.stderr)
        self.assertNotIn('should-not-start', result.stderr)


if __name__ == '__main__':
    unittest.main()
