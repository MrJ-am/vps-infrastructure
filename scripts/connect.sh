#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
key=${VPS_SSH_KEY:-"$HOME/.ssh/matheval_admin"}
if [ ! -r "$key" ]; then
    echo "Clé privée indisponible. Voir docs/ACCES.md." >&2
    exit 1
fi
exec ssh -i "$key" -o BatchMode=yes -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$script_dir/ssh-known-hosts" \
    -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    root@187.77.95.158 "$@"
