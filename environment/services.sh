#!/usr/bin/env bash
set -euo pipefail
environment_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$environment_dir/environment.py" services "$@"

