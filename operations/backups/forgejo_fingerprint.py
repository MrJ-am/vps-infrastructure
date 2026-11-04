"""Content-only fingerprint; never prints database or repository contents."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys


def fingerprint(dump, roots, restore):
    digest = hashlib.sha256()
    def add(raw):
        digest.update(len(raw).to_bytes(8, 'big'))
        digest.update(raw)
    process = subprocess.Popen([restore, '--file=-', str(dump)], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    try:
        for line in process.stdout:
            # PostgreSQL generates a new client-side restriction token on each
            # SQL export. It is not database content. COPY escapes backslashes.
            if line.startswith((b'\\restrict ', b'\\unrestrict ')):
                continue
            add(line)
        if process.wait() != 0:
            raise RuntimeError('Database fingerprint failed')
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()
    for root in roots:
        root = Path(root)
        for path in [root, *sorted(root.rglob('*'))]:
            info = path.lstat()
            add(str(Path(root.name) / path.relative_to(root)).encode())
            add(f'{info.st_mode}:{info.st_uid}:{info.st_gid}'.encode())
            for name in sorted(os.listxattr(path, follow_symlinks=False)):
                add(name.encode())
                add(os.getxattr(path, name, follow_symlinks=False))
            if stat.S_ISLNK(info.st_mode):
                add(os.readlink(path).encode())
            elif stat.S_ISREG(info.st_mode):
                content = hashlib.sha256()
                with path.open('rb') as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b''):
                        content.update(chunk)
                add(content.digest())
            elif not stat.S_ISDIR(info.st_mode):
                raise RuntimeError('Unsupported backup file type')
    return digest.hexdigest()


if __name__ == '__main__':
    print(fingerprint(Path(sys.argv[1]), sys.argv[3:], sys.argv[2]))
