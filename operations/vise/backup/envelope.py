"""Encrypt a private paired snapshot and verify ciphertext before publication."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import capture as C

FILES = ('database.dump', 'deletions.log')
AGE = re.compile(r'age1[a-z0-9]{58}')


def write_json(path, value):
    with Path(path).open('xb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        output.flush()
        os.fsync(output.fileno())


class Envelope:
    # Nonzero owner/group is for invented local fixtures only. The installed
    # entrypoint always supplies root and a fixed destination/credential.
    def __init__(self, tools, owner=0, group=0):
        self.tools, self.owner, self.group = tools, owner, group

    def run(self, args, output=None):
        try:
            result = subprocess.run(args, stdin=subprocess.DEVNULL,
                stdout=output or subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={'LC_ALL': 'C'}, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            raise C.Refused('VISE_BACKUP_ENVELOPE_COMMAND_REFUSED') from None
        C.require(result.returncode == 0, 'VISE_BACKUP_ENVELOPE_COMMAND_REFUSED')

    def digest(self, path):
        return C.hash_private(path, self.owner, 10 * 1024**3, self.group)

    def publish(self, root, identifier, recipient):
        C.require(type(identifier) is str and re.fullmatch('[0-9a-f]{32}', identifier),
                  'VISE_BACKUP_IDENTIFIER_REFUSED')
        C.require(type(recipient) is str and AGE.fullmatch(recipient), 'VISE_BACKUP_RECIPIENT_REFUSED')
        root = Path(root)
        C.directory(root, self.owner, self.group)
        work = root / ('.' + identifier + '.pending')
        source = work / 'components'
        C.directory(work, self.owner, self.group)
        C.directory(source, self.owner, self.group)
        C.require({p.name for p in source.iterdir()} == set(FILES), 'VISE_BACKUP_COMPONENTS_REFUSED')
        C.require({p.name for p in work.iterdir()} == {'components'}, 'VISE_BACKUP_ENVELOPE_ALREADY_STARTED')
        for name in FILES:
            self.digest(source / name)
        bundle = work / 'components.tar'
        with bundle.open('xb') as output:
            os.fchmod(output.fileno(), 0o600)
            self.run([self.tools['tar'], '-C', str(source), '-cf', '-', '--', *FILES], output)
        key = work / 'ephemeral-key'
        self.run([self.tools['age_keygen'], '-o', str(key)])
        key.chmod(0o600)
        public_path = work / 'ephemeral-public'
        with public_path.open('xb') as output:
            os.fchmod(output.fileno(), 0o600)
            self.run([self.tools['age_keygen'], '-y', str(key)], output)
        fd, _ = C.regular(public_path, self.owner, 128, self.group)
        with os.fdopen(fd, 'r') as stream:
            public = stream.read().strip()
        C.require(AGE.fullmatch(public), 'VISE_BACKUP_ENVELOPE_KEY_REFUSED')
        publication = work / 'publication'
        publication.mkdir(mode=0o700)
        encrypted = publication / 'components.tar.age'
        encrypted_key = publication / 'key.age'
        self.run([self.tools['age'], '-r', public, '-o', str(encrypted), str(bundle)])
        self.run([self.tools['age'], '-r', recipient, '-o', str(encrypted_key), str(key)])
        verified = work / 'verified.tar'
        self.run([self.tools['age'], '-d', '-i', str(key), '-o', str(verified), str(encrypted)])
        for path in (verified, encrypted, encrypted_key):
            path.chmod(0o600)
        C.require(self.digest(verified) == self.digest(bundle), 'VISE_BACKUP_CIPHERTEXT_REFUSED')
        write_json(publication / 'manifest.json', {
            'schema_version': 1, 'kind': 'vise-paired-backup', 'capture_id': identifier,
            'created': int(time.time()), 'components': list(FILES),
            'offline_pair': True, 'requires_current_erasure_journal': True,
            'files': {p.name: self.digest(p) for p in (encrypted, encrypted_key)}
        })
        for path in publication.iterdir():
            fd, _ = C.regular(path, self.owner, 10 * 1024**3, self.group)
            try: os.fsync(fd)
            finally: os.close(fd)
        C.sync(publication)
        target = root / identifier
        C.require(not target.exists() and not target.is_symlink(), 'VISE_BACKUP_PUBLICATION_EXISTS')
        # The caller holds the exclusive deployment lock. No other identity
        # has write access to this root-owned private directory.
        os.rename(publication, target)
        C.sync(root)
        shutil.rmtree(work)
        C.sync(root)
        return target
