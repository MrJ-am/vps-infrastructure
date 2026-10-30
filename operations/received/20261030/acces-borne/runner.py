"""Entrée fixe non privilégiée ; installation et ACL SSH détenues par root.

Le seul flux admis est la concaténation des trois fichiers exacts de l'archive.
Aucun chemin, argument de commande, secret ou diagnostic n'est transmis.
"""
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile


ROOT = Path("/var/lib/mrjam-inventory-access")
MAGIC = b"MRJAM-INVENTORY-V1\n"
RUNTIME = (
    ("inventory.py", 11613, "b4abbdd8afbd1216cde98bf001ea0908ad3fb90d3068272db3e19d58edc80a45"),
    ("validate_report.py", 4603, "212e4d78986c4d5421f09004982d9ca3cd436a629e6c044ca85bce0f186342e0"),
    ("inventory.schema.json", 22136, "86f9a82d9f9f4881156b5fa10afd41a0ee912930cd62df3f347fcc29f0e202f5"),
)
INPUT_SIZE = len(MAGIC) + sum(size for _, size, _ in RUNTIME)
MAX_REPORT = 16384
PIPELINE = """set +x
exec 2>/dev/null
set -u
umask 077
[[ "$UID" -ne 0 && "$EUID" -ne 0 ]] || exit 64
set -o noclobber
set -o pipefail
python3 -I -S ./inventory.py 2>/dev/null |
  python3 -I -S ./validate_report.py 2>/dev/null \\
    > inventaire-borne-filtre.json
"""


def unpack(data):
    if len(data) != INPUT_SIZE or not data.startswith(MAGIC):
        raise ValueError()
    position = len(MAGIC)
    files = {}
    for name, size, digest in RUNTIME:
        value = data[position:position + size]
        if hashlib.sha256(value).hexdigest() != digest:
            raise ValueError()
        files[name] = value
        position += size
    return files


def deadline(_signum, _frame):
    raise TimeoutError()


def main():
    if len(sys.argv) != 1 or os.getuid() == 0 or os.geteuid() == 0:
        return 64
    os.umask(0o077)
    try:
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(15)
        data = sys.stdin.buffer.read(INPUT_SIZE + 1)
        signal.alarm(0)
        files = unpack(data)
    except Exception:
        return 65
    try:
        # The parent is the only directory writable by this dedicated account.
        work = Path(tempfile.mkdtemp(prefix="lot-", dir=ROOT / "work"))
        for name, value in files.items():
            with (work / name).open("xb") as handle:
                handle.write(value)
        # Check the actual files again before their execution.
        for name, size, digest in RUNTIME:
            value = (work / name).read_bytes()
            if len(value) != size or hashlib.sha256(value).hexdigest() != digest:
                return 66
        result = subprocess.run(
            ["/run/current-system/sw/bin/bash", "--noprofile", "--norc", "-p", "-c", PIPELINE],
            cwd=work, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=60, check=False,
            env={"PATH": str(Path(sys.executable).parent) + ":/run/current-system/sw/bin",
                 "LANG": "C", "LC_ALL": "C"},
        )
        if result.returncode:
            return 67
        # No JSON crosses SSH before the successful pipefail exit.
        with (work / "inventaire-borne-filtre.json").open("rb") as handle:
            report = handle.read(MAX_REPORT + 1)
        if not 0 < len(report) <= MAX_REPORT:
            return 68
        sys.stdout.buffer.write(report)
        sys.stdout.buffer.flush()
        return 0
    except subprocess.TimeoutExpired:
        return 69
    except Exception:
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
