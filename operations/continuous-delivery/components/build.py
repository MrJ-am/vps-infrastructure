"""Offline build entry point, invoked only inside the Nix derivations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

from prepare import inventory

HERE = Path(__file__).resolve().parent


def run(*args, cwd):
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def binary_link(directory, name, target):
    destination = directory / 'node_modules/.bin' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    destination.symlink_to(target)


def test_vise_api(app, work):
    """An isolated synthetic PostgreSQL cluster and real candidate backend."""
    data, socket = work / 'pgdata', work / 'pgsocket'
    socket.mkdir()
    run('initdb', '-D', data, '-A', 'trust', '-U', 'carnet', '--no-locale', cwd=work)
    run('pg_ctl', '-D', data, '-l', work / 'postgres.log', '-o', '-h 127.0.0.1 -p 55439 -k ' + str(socket), '-w', 'start', cwd=work)
    backend = None
    try:
        run('createdb', '-h', socket, '-p', '55439', '-U', 'carnet', 'carnet', cwd=work)
        env = dict(os.environ, CARNET_DB_HOST='127.0.0.1', CARNET_DB_PORT='55439',
                   CARNET_DB_NAME='carnet', CARNET_DB_USER='carnet', CARNET_DB_PASSWORD='synthetic',
                   CARNET_PUBLIC_URL='http://localhost:3000', CARNET_BIND='127.0.0.1:30139',
                   CARNET_DELETION_LEDGER=str(work / 'deletions.log'), CARNET_DIST=str(app / 'dist'),
                   CARNET_SCHEMA_MODE='initialize-v1')
        with (work / 'backend.log').open('w') as log:
            backend = subprocess.Popen([work / 'target/release/etp-carnet-server'], cwd=app, env=env, stdout=log, stderr=log)
            for attempt in range(100):
                if backend.poll() is not None:
                    raise RuntimeError('SYNTHETIC_BACKEND_EXITED: ' + (work / 'backend.log').read_text())
                try:
                    with urllib.request.urlopen('http://127.0.0.1:30139/api/health', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('SYNTHETIC_BACKEND_NOT_READY')
            subprocess.run(['node', '--import', 'tsx', '--test', 'tests/api.test.ts'], cwd=app,
                           env=dict(env, CARNET_API_TEST_URL='http://127.0.0.1:30139'), check=True)
    finally:
        if backend is not None:
            backend.terminate()
            try:
                backend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                backend.kill()
                backend.wait()
        run('pg_ctl', '-D', data, '-m', 'immediate', '-w', 'stop', cwd=work)


def build(inputs, output, kind, source):
    manifest = json.loads((inputs / 'manifest.json').read_text())
    actual = inventory(inputs)
    actual.pop('manifest.json')
    if actual != manifest['files']:
        raise ValueError('INPUT_CONTENT_MISMATCH')
    work = Path.cwd() / 'work'
    shutil.copytree(inputs, work, symlinks=True)
    work.chmod(work.stat().st_mode | 0o700)
    for path in work.rglob('*'):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | (0o700 if path.is_dir() else 0o200))
    os.environ.update(ELM_HOME=str(work / 'elm-home'), HOME=str(work / 'home'), GHCRTS='-N2')
    Path(os.environ['HOME']).mkdir()
    # elm-test otherwise spawns one process for every CPU on the build host.
    cpu_limit = work / 'test-cpus.cjs'
    cpu_limit.write_text("const os=require('node:os');const cpus=os.cpus;os.cpus=()=>cpus().slice(0,2);\n")
    os.environ['NODE_OPTIONS'] = '--require=' + str(cpu_limit)
    pins = manifest['pins']
    output.mkdir(parents=True)
    elm_test = work / 'tools/node_modules/elm-test/bin/elm-test'
    lines = elm_test.read_text().splitlines(keepends=True)
    elm_test.write_text('#!' + shutil.which('node') + '\n' + ''.join(lines[1:]))
    tools = work / 'tools/node_modules/.bin'
    os.environ['PATH'] = str(tools) + ':' + os.environ['PATH']
    binary_link(work / 'tools', 'elm', shutil.which('elm'))
    names = ['vise'] if kind == 'vise' else ['log', 'audition', 'vision', 'mateval', 'logique']
    for name in names:
        app = work / 'apps' / name
        binary_link(app, 'elm', shutil.which('elm'))
        binary_link(app, 'elm-test', tools / 'elm-test')
        binary_link(app, 'elm-format', shutil.which('elm-format'))
        os.environ['GITHUB_SHA'] = pins['applications'].get(name, ['', 'infrastructure-candidate'])[1]
        if name in ('log', 'audition'):
            style = work / 'styles' / pins['styles'][name]
            shutil.copytree(style, app / '.dependances/style-mrjam')
            run('node', '--check', 'pont.js', cwd=app)
            run(tools / 'elm-test', '--compiler', shutil.which('elm'), cwd=app)
            run('elm', 'make', 'src/Main.elm', '--optimize', '--output=elm.js', cwd=app)
            site = app / 'site'
            site.mkdir()
            for filename in ('index.html', 'pont.js', 'elm.js'):
                shutil.copy2(app / filename, site / filename)
            shutil.copytree(style / 'public/assets', site / 'assets', dirs_exist_ok=True)
            shutil.copytree(work / 'resources' / name, site, dirs_exist_ok=True)
        elif name == 'vision':
            interface = app / 'interface'
            run('node', '--check', 'pont.js', cwd=interface)
            run('node', '--check', 'exports.js', cwd=interface)
            # Tests use the same local common sources as the production compiler.
            style = work / 'styles' / pins['styles'][name]
            shutil.copytree(style, interface / '.dependances/style-mrjam')
            run('python3', 'tests/architecture.py', cwd=interface)
            run(tools / 'elm-test', '--compiler', shutil.which('elm'), cwd=interface)
            run('python3', 'compiler.py', '--style', style, '--elm', shutil.which('elm'), '--elm-format', shutil.which('elm-format'), cwd=interface)
            site = interface / 'dist'
        elif name == 'mateval':
            os.environ['STYLE_MRJAM_SOURCE'] = str(work / 'styles' / pins['styles'][name])
            run('node', 'scripts/test-elm.cjs', cwd=app)
            run('node', '--test', *sorted((app / 'tests/construction').glob('*.test.cjs')), cwd=app)
            run('node', 'scripts/check-artifacts.mjs', cwd=app)
            run('node', 'scripts/build-elm.cjs', cwd=app)
            run('node', 'scripts/version-assets.cjs', cwd=app)
            site = app / 'site'
        elif name == 'logique':
            shutil.copytree(work / 'styles' / pins['styles'][name], app / '.cache/style-mrjam')
            run('python3', 'scripts/build_data.py', '--check', cwd=app)
            run('node', 'scripts/test.mjs', cwd=app)
            run('node', 'scripts/test-atelier.mjs', cwd=app)
            run('node', 'scripts/build.mjs', cwd=app)
            run('node', 'scripts/preparer-identite.mjs', cwd=app)
            site = app / '.cache/site-complet'
        else:
            os.environ.update(CARGO_HOME=str(work / 'cargo-home'), CARGO_TARGET_DIR=str(work / 'target'),
                              CARGO_BUILD_JOBS='2', RUSTFLAGS='--remap-path-prefix=' + str(work) + '=vise-source')
            (app / '.cargo').mkdir(exist_ok=True)
            (app / '.cargo/config.toml').write_text('[source.crates-io]\nreplace-with="vendored-sources"\n[source.vendored-sources]\ndirectory=' + json.dumps(str(work / 'cargo-vendor')) + '\n[net]\noffline=true\n')
            run('cargo', 'build', '--release', '--frozen', '--offline', '--manifest-path', 'backend/Cargo.toml', cwd=app)
            # No Rust unit tests at this pin; exercise the real backend via API below.
            run('node', 'scripts/build.mjs', cwd=app)
            run('node', 'node_modules/typescript/bin/tsc', '--noEmit', cwd=app)
            run('node', '--import', 'tsx', '--test', 'tests/crypto.test.ts', 'tests/contenu.test.ts', 'tests/image.test.ts', 'tests/poll.test.ts', cwd=app)
            test_vise_api(app, work)
            shutil.copy2(work / 'target/release/etp-carnet-server', output / 'server')
            shutil.copytree(app / 'dist', output / 'dist')
            continue
        destination = output / name
        shutil.copytree(site, destination)
        run('python3', source / 'operations/builds/check_frontend_site.py', '--site', destination, cwd=app)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=('frontends', 'vise'))
    parser.add_argument('inputs', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    build(args.inputs, args.output, args.kind, args.source)
