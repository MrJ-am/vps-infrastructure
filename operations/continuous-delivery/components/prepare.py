"""Public dependency preparation. No deployment, services, or production data.

prepare(source: Path, cache: Path, export: Callable[[str,str,Path],None])
returns {inputs: str, manifest_sha256: str}. export is ci.export (bare repo name).
The caller supplies candidate infrastructure sources; only this module uses network.
"""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.request

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent.parent / 'builds'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target) or not path.resolve().is_relative_to(root.resolve()) or not path.resolve().is_file():
                raise ValueError('INPUT_LINK_ESCAPES_OR_NOT_FILE')
            result[name] = {'link': target}
        elif path.is_file():
            result[name] = {'sha256': sha(path.read_bytes()), 'executable': bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise ValueError('INPUT_SPECIAL_FILE')
    return result


def copy(source, destination):
    inventory(source)  # Refuse escaping links before copying.
    shutil.copytree(source, destination, symlinks=True,
                    ignore=shutil.ignore_patterns('.git', 'node_modules', 'elm-stuff', 'target', '.delivery-inputs'))


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise ValueError('PUBLIC_ARCHIVE_TOO_LARGE')
    return data


def npm(directory, cache):
    lock = json.loads((directory / 'package-lock.json').read_text())
    for name, entry in lock['packages'].items():
        if name and (not entry.get('resolved', '').startswith('https://registry.npmjs.org/')
                     or not entry.get('integrity', '').startswith('sha512-')):
            raise ValueError('NPM_ORIGIN_OR_INTEGRITY_REFUSED')
    subprocess.run(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund',
                    '--registry=https://registry.npmjs.org', '--cache=' + str(cache)],
                   cwd=directory, check=True, timeout=900, stdin=subprocess.DEVNULL)
    inventory(directory / 'node_modules')


def prepare(source: Path, cache: Path, export):
    source, cache = Path(source).resolve(), Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    destination = source / '.delivery-inputs'
    if destination.exists() or destination.is_symlink():
        raise ValueError('NEW_INPUT_DESTINATION_REQUIRED')
    pins = json.loads((HERE / 'pins.json').read_text())
    helper = load(BUILD / 'prepare.py', '_component_cargo_inputs')
    with tempfile.TemporaryDirectory(prefix='components-', dir=source) as temporary:
        root = Path(temporary)
        exported = {}
        def external(repo, revision):
            key = (repo, revision)
            if key not in exported:
                target = cache / 'sources' / (repo + '-' + revision)
                record = target.with_suffix('.inventory.json')
                if target.exists():
                    if not record.is_file() or inventory(target) != json.loads(record.read_text()):
                        raise ValueError('SOURCE_CACHE_CONTENT_MISMATCH')
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    staging = target.with_name(target.name + '.partial')
                    if staging.exists():
                        shutil.rmtree(staging)
                    export(repo, revision, staging)
                    values = inventory(staging)
                    staging.rename(target)
                    record.write_text(json.dumps(values, sort_keys=True))
                exported[key] = target
            return exported[key]
        for name in ('log', 'audition'):
            copy(source / ('interface-' + name), root / 'apps' / name)
        for name, (repo, revision) in pins['applications'].items():
            app = external(repo, revision)
            if name == 'mateval':
                app = app / 'frontend'
            copy(app, root / 'apps' / name)
        for revision in sorted(set(pins['styles'].values())):
            copy(external('style-mrjam', revision), root / 'styles' / revision)
        # Existing resource lock covers all additional Log/Audition site files.
        resources = json.loads((BUILD / 'frontend-resources-operationnel-20261030.lock.json').read_text())['files']
        katex = [entry for entry in resources if entry['source_path'].startswith('katex-dist/')]
        public = {}
        if katex:
            import base64
            provenance = katex[0]['provenance']
            raw = fetch(provenance['url'])
            if sha(raw) != provenance['archive_sha256'] or 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode() != provenance['integrity']:
                raise ValueError('KATEX_ARCHIVE_MISMATCH')
            with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
                for entry in katex:
                    name = entry['source_path']
                    member = archive.getmember('package/dist/' + name.removeprefix('katex-dist/'))
                    if not member.isfile():
                        raise ValueError('KATEX_MEMBER_TYPE')
                    public[name] = archive.extractfile(member).read()
        for entry in resources:
            if entry['frontend'] not in ('log', 'audition'):
                continue
            provenance = entry['provenance']
            if entry['source_path'].startswith('signature/'):
                raw = (external('Signature', provenance['revision']) / provenance['path']).read_bytes()
                if hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != provenance['git_blob']:
                    raise ValueError('SIGNATURE_BLOB_MISMATCH')
            else:
                raw = public[entry['source_path']]
            if sha(raw) != entry['sha256']:
                raise ValueError('RESOURCE_HASH_MISMATCH')
            helper.put(root / 'resources' / entry['frontend'], entry['destination'], raw)
        copy(external('Signature', pins['signature']), root / 'apps/logique/.cache/signature')
        elm_lock = json.loads((BUILD / 'elm-dependencies.lock.json').read_text())
        elm_lock['packages'].update(json.loads((HERE / 'elm-extra.lock.json').read_text())['packages'])
        registry = helper.checked_bytes(BUILD, 'elm-registry.dat', elm_lock['registry_sha256'])
        helper.put(root / 'elm-home/0.19.1/packages', 'registry.dat', registry)
        for name, entry in elm_lock['packages'].items():
            saved = cache / 'elm' / name / entry['version']
            if not saved.exists():
                raw = fetch('https://github.com/' + name + '/archive/refs/tags/' + entry['version'] + '.tar.gz')
                with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
                    members = {m.name.split('/', 1)[1]: m for m in archive.getmembers() if '/' in m.name and m.isfile()}
                    for filename, checksum in entry['files'].items():
                        data = archive.extractfile(members[filename]).read()
                        if sha(data) != checksum:
                            raise ValueError('ELM_ARCHIVE_HASH_MISMATCH')
                        helper.put(saved, filename, data)
            for filename, checksum in entry['files'].items():
                helper.put(root / 'elm-home/0.19.1/packages' / name / entry['version'], filename,
                           helper.checked_bytes(saved, filename, checksum))
        for name in ('log','audition','vision','mateval','logique','vise'):
            app = root / 'apps' / name
            elm_file = app / ('interface/elm.json' if name == 'vision' else 'elm.json')
            elm = json.loads(elm_file.read_text())
            for category in ('dependencies', 'test-dependencies'):
                for section in elm.get(category, {}).values():
                    for package, version in section.items():
                        if elm_lock['packages'].get(package, {}).get('version') != version:
                            raise ValueError('ELM_LOCK_INCOMPLETE:' + package)
            if name in ('logique','vise'):
                npm(app, cache / 'npm')
        copy(HERE / 'tools', root / 'tools')
        npm(root / 'tools', cache / 'npm')
        cargo = tomllib.loads((root / 'apps/vise/backend/Cargo.lock').read_text())
        for package in cargo['package']:
            if not package.get('source'):
                continue
            if package['source'] != helper.REGISTRY:
                raise ValueError('CARGO_ORIGIN_REFUSED')
            data = helper.crate_archive(cache / 'cargo', package, True)
            for filename, value in helper.crate_files(data, package).items():
                helper.put(root / 'cargo-vendor', package['name'] + '-' + package['version'] + '/' + filename, value)
        manifest = {'schema_version': 1, 'pins': pins, 'files': inventory(root)}
        data = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
        (root / 'manifest.json').write_bytes(data)
        root.rename(destination)
    return {'inputs': str(destination), 'manifest_sha256': sha(data)}
