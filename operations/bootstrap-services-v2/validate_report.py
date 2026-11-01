import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).absolute().parent))
from contract import MAX_BYTES, decode

if __name__ == "__main__":
    try:
        if len(sys.argv) != 1:
            raise ValueError("arguments")
        sys.stdout.buffer.write(decode(sys.stdin.buffer.read(MAX_BYTES + 1)))
    except Exception:
        sys.stderr.write("SERVICE_REPORT_REJECTED\n")
        raise SystemExit(65)
