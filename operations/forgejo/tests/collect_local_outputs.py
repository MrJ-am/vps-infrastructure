#!/usr/bin/env python3
"""Export only public outputs of a completed local dedicated-UID qualification.

Run in the offline Cloud Nix fixture. No production collector or filesystem is
accepted; diagnostics and incomplete runs can never supply this export.
"""
import hashlib
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path('/workspace/shared/mrjam-declarative-nix')
SCRIPT = Path(__file__).resolve().parents[2] / 'release/import_qualified.py'
spec = importlib.util.spec_from_file_location('qualified_import', SCRIPT)
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


def qualification_json(raw):
    # The completed local receipt records fractional elapsed seconds. That is
    # metadata, never an artifact size, UID, revision or authority decision.
    # Keep integer-only parsing for the export, artifact lock and verifier.
    def pairs(items):
        value = {}
        for key, item in items:
            pack.require(key not in value, 'DUPLICATE_FIELD')
            value[key] = item
        return value

    def invalid(_):
        raise pack.Refused('QUALIFICATION_NUMBER_REFUSED')

    value = json.loads(raw, object_pairs_hook=pairs, parse_float=Decimal, parse_constant=invalid)
    pack.require(type(value) is dict and 'duration_seconds' in value, 'QUALIFICATION_DURATION_REQUIRED')
    duration = value.pop('duration_seconds')
    pack.require(type(duration) in (int, Decimal) and 0 < duration <= 1860, 'QUALIFICATION_DURATION_REFUSED')
    # Decimal elsewhere cannot be serialized: fractional security fields fail.
    try:
        result = pack.parse(json.dumps(value, allow_nan=False).encode())
    except (TypeError, ValueError):
        raise pack.Refused('QUALIFICATION_NUMBER_REFUSED') from None
    result['duration_seconds'] = duration
    return result


def main():
    pack.require(os.getuid() == 0 and os.environ.get('MRJAM_SYNTHETIC_CONTAINER') == '1'
                 and set(os.listdir('/sys/class/net')) == {'lo'} and len(sys.argv) == 2
                 and re.fullmatch(r'worker-[A-Za-z0-9_-]+', sys.argv[1]), 'OFFLINE_LOCAL_FIXTURE_REQUIRED')
    name = sys.argv[1]
    exported = ROOT / name
    output = ROOT / 'qualifier-uid-59990' / (name + '-outputs')
    for path, uid, mode in ((exported, 0, 0o555), (output.parent, 59990, 0o700), (output, 59990, 0o700)):
        info = path.lstat()
        pack.require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid
                     and stat.S_IMODE(info.st_mode) == mode, 'FIXTURE_OWNERSHIP_REFUSED')
    pack.require(set(os.listdir(output)) == {'server', 'frontend.tar', 'verification.json', 'qualification.json'}, 'COMPLETE_OUTPUTS_REQUIRED')
    raw = pack.read_file(exported / 'export.json', 1048576)
    export = pack.parse(raw)
    qualification_raw = pack.read_file(output / 'qualification.json', 65536)
    qualification = qualification_json(qualification_raw)
    pack.require(qualification['decision'] == 'passed' and qualification['fixture_uid'] == 59990
                 and qualification['isolated_uid_fixture'] is True
                 and qualification['export_sha256'] == pack.sha(raw)
                 and qualification['proposal_sha256'] == export['proposal_sha256']
                 and qualification['rules_revision'] == export['configuration']['rules_revision']
                 and qualification['validator_store'] == export['configuration']['validator_store'], 'QUALIFICATION_BINDING_REFUSED')
    files = {}
    pins = {}
    pack.require(type(qualification['artifacts']) is list and len(qualification['artifacts']) == 3, 'ARTIFACT_LIST_REFUSED')
    for entry in qualification['artifacts']:
        pack.exact(entry, ('name', 'bytes', 'sha256'))
        name = entry['name']
        pack.require(name in pack.LIMITS and name not in pins, 'ARTIFACT_LIST_REFUSED')
        path = output / name
        info = path.lstat()
        pack.require(stat.S_ISREG(info.st_mode) and info.st_uid == 59990 and info.st_nlink == 1
                     and stat.S_IMODE(info.st_mode) == 0o400, 'ARTIFACT_OWNERSHIP_REFUSED')
        data = pack.read_file(path, pack.LIMITS[name])
        pack.require(len(data) == entry['bytes'] and pack.sha(data) == entry['sha256'], 'ARTIFACT_HASH_MISMATCH')
        files[name] = data
        pins[name] = {key: entry[key] for key in ('bytes', 'sha256')}
    receipt = pack.parse(files['verification.json'])
    lock = {'schema_version': 1, 'kind': 'mrjam-qualified-artifact-import', 'files': pins,
            'proposal_sha256': qualification['proposal_sha256'], 'rules_revision': qualification['rules_revision'],
            'policy_sha256': receipt['policy_sha256']}
    lock_raw = (json.dumps(lock, sort_keys=True, indent=2) + '\n').encode()
    pack.checked_inputs(output, lock_raw)
    pack.frontend_files(files['frontend.tar'])
    target = ROOT / (sys.argv[1] + '-qualified-public')
    target.mkdir(mode=0o700)  # No prior export or receipt is replaced.
    for name, data in {**files, 'qualification.json': qualification_raw, 'import.lock.json': lock_raw}.items():
        with (target / name).open('xb') as stream:
            stream.write(data)
        (target / name).chmod(0o444)
    target.chmod(0o555)
    print(json.dumps({'decision': 'exported-public-qualified-code', 'directory': target.name,
                      'lock_sha256': pack.sha(lock_raw), 'production_authorized': False}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Public local fixtures only; never echo a path, response or traceback.
        code = str(error) if type(error) is pack.Refused and re.fullmatch(r'[A-Z_]{1,80}', str(error)) else 'LOCAL_EXPORT_FAILED'
        print(json.dumps({'decision': 'refused', 'code': code, 'production_authorized': False}, sort_keys=True))
        raise SystemExit(2) from None
