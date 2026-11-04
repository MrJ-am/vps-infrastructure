#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 1 || ! $1 =~ ^native-[0-9]{3}\.json$ ]]; then
  exit 64
fi
task_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
task_workspace=$(cd -- "$task_dir/../../.." && pwd)
mkdir -p "$task_dir/results"
exec /nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0/bin/bwrap \
  --unshare-all --die-with-parent --new-session \
  --ro-bind /nix/store /nix/store \
  --ro-bind "$task_dir" /tests \
  --ro-bind "$task_workspace/operations/identity/acceptance" /acceptance \
  --ro-bind /nix/store/1n0p3fn7nfdbwvpkbqlnk7y13057mivk-mrjam-identity-0.1.0/bin/mrjam-identity /candidate \
  --bind "$task_dir/results" /output --tmpfs /tmp --proc /proc --dev /dev \
  --dir /etc --ro-bind "$task_dir/passwd" /etc/passwd --ro-bind "$task_dir/group" /etc/group \
  --ro-bind "$task_dir/hosts" /etc/hosts \
  --dir /bin --symlink /nix/store/kwyi4bq5s2qgwbhz6cs4gjy57c2zdxws-bash-interactive-5.3p20/bin/bash /bin/sh \
  --clearenv --setenv HOME /tmp --setenv LANG C --setenv TZ UTC \
  /nix/store/sgd4bw41gdw6rhla06bw7knzbl9gxzcb-python3-3.14.8/bin/python3 -B /tests/qualify.py \
  --binary /candidate --kanidm /nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2 \
  --postgres-bin /nix/store/f5bx5vyjvfc52a93q6p7gy7aidwg3jpx-postgresql-17.11/bin \
  --openssl /nix/store/gvglnxscmvx4mh9my0cy0xgi0l1z6l9s-openssl-3.5.9-bin/bin/openssl \
  --output "/output/$1"
