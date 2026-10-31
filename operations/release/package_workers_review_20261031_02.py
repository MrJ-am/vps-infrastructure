#!/usr/bin/env python3
"""Package only the explicitly selected, already verified public review files."""
from pathlib import Path
import gzip
import hashlib
import io
import json
import tarfile

ROOT = Path('/workspace/shared/mrjam-declarative-nix/review-export-workers-20261031-02')
ARCHIVE = Path('/workspace/shared/mrjam-travailleurs-revue-20261031-02.tar')
MANIFEST_SHA256 = '8299c081d29d4f0301c873307d3fb0d4ecc2a67fd40d2033b3f0c6f7ec3ebdff'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def require(ok):
    if not ok:
        raise ValueError('REVIEW_PACKAGE_REFUSED')


def package():
    require(ROOT.resolve() == ROOT and not ARCHIVE.exists())
    require(digest(ROOT / 'review-manifest.json') == MANIFEST_SHA256)
    manifest = json.loads((ROOT / 'review-manifest.json').read_bytes())
    require(manifest['production_ready'] is False and manifest['production_authorized'] is False)
    selection_bytes = (ROOT / 'selection.json').read_bytes()
    require(hashlib.sha256(selection_bytes).hexdigest() == manifest['selection_sha256'])
    selection = json.loads(selection_bytes)
    names = ['selection.json', 'review-manifest.json', 'public-artifacts.nix-export.gz']
    names.extend('evidence/' + n for n in selection['evidence_sha256'])
    for n, expected in selection['evidence_sha256'].items():
        require(digest(ROOT / ('evidence/' + n)) == expected)
    for n, entry in manifest['exports'].items():
        require((ROOT / n).stat().st_size == entry['bytes'] and digest(ROOT / n) == entry['sha256'])
    # The compressed stream must also yield the exact originally imported stream.
    with gzip.open(ROOT / 'public-artifacts.nix-export.gz', 'rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() ==
                manifest['exports']['public-artifacts.nix-export']['sha256'])
    sums = {n: digest(ROOT / n) for n in sorted(names)}
    checksums = ''.join(f'{h}  {n}\n' for n, h in sums.items()).encode()
    # SHA256SUMS describes only members actually carried in this archive.
    with tarfile.open(ARCHIVE, 'x', format=tarfile.USTAR_FORMAT) as archive:
        for n in sorted(names) + ['SHA256SUMS']:
            item = tarfile.TarInfo(n)
            item.mode = 0o444
            item.uid = item.gid = item.mtime = 0
            if n == 'SHA256SUMS':
                item.size = len(checksums)
                archive.addfile(item, io.BytesIO(checksums))
            else:
                path = ROOT / n
                require(path.resolve() == path and path.is_file())
                item.size = path.stat().st_size
                with path.open('rb') as stream:
                    archive.addfile(item, stream)
    with tarfile.open(ARCHIVE, 'r') as archive:
        require(sorted(archive.getnames()) == sorted(names + ['SHA256SUMS']))
        for member in archive.getmembers():
            require(member.isfile() and member.mode == 0o444)
            with archive.extractfile(member) as stream:
                expected = hashlib.sha256(checksums).hexdigest() if member.name == 'SHA256SUMS' else sums[member.name]
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == expected)
    return {'archive': str(ARCHIVE), 'sha256': digest(ARCHIVE), 'bytes': ARCHIVE.stat().st_size,
            'members': len(names) + 1, 'all_members_verified': True,
            'compressed_stream_matches_imported_stream': True, 'production_ready': False}


if __name__ == '__main__':
    print(json.dumps(package(), sort_keys=True))
