"""Preserve existing runtime manifest contracts; hash final fixed-up bytes."""
import hashlib
import json
from pathlib import Path
import re
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(root, metadata, payload_field='payload_sha256'):
    manifest = root / 'artifact.json'
    manifest.unlink(missing_ok=True)
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('ARTIFACT_SYMLINK_REFUSED')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = digest(path)
    manifest.write_text(json.dumps(dict(metadata, **{payload_field: files}), indent=2, sort_keys=True) + '\n')


def finalize(kind, inputs, output, revision, toolchains_lock):
    pins = json.loads((inputs / 'manifest.json').read_text())['pins']
    input_digest = digest(inputs / 'manifest.json')
    if kind == 'vise':
        import shutil
        for name in ('LICENSE', 'COPYING'):
            target = output / 'share/licenses/vise' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(inputs / 'apps/vise' / name, target)
        record(output, {
            'schema_version': 1,
            'repository': 'https://github.com/MrJ-am/etp-vie-affective',
            'revision': pins['applications']['vise'][1],
            'materialization_sha256': input_digest,
            'crypto_format': 1,
            'production_qualification': False,
        }, 'files_sha256')
    else:
        if not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('EXACT_INFRASTRUCTURE_REVISION_REQUIRED')
        for name in ('log', 'audition', 'vision', 'mateval', 'logique'):
            style = pins['styles'][name]
            identity = json.loads((inputs / 'styles' / style / 'identite.json').read_text())
            commits = {
                'infrastructure': revision,
                name: pins['applications'].get(name, ['', revision])[1],
                'style': style,
                'signature': identity['revision'],
                'signature_resources': pins['signature'],
            }
            if any(not re.fullmatch('[0-9a-f]{40}', value) for value in commits.values()):
                raise ValueError('SOURCE_COMMIT_INVALID')
            record(output / name, {
                'schema_version': 1,
                'artifact': name + '-elm',
                'source_commits': commits,
                'style_revision': style,
                'input_manifest_sha256': input_digest,
                'toolchains_lock_sha256': digest(toolchains_lock),
                'deployment_authorized': False,
                'runtime_qualification': 'Source/build tests passed; browser and deployed runtime qualification not established by this build.',
            })


if __name__ == '__main__':
    finalize(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5]))
