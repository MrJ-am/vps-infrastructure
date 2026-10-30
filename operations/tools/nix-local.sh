#!/usr/bin/env bash
# Local disposable Cloud tooling, never a VPS runner or deployment interface.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
task_image='nixos/nix@sha256:c03c1081ba8fb98528dee2a677dee6f42bdddb6b90e1c14c67aba8c1e31ed4bb'
task_volume='mrjam-declarative-nix-store-20261030'
task_output='/workspace/shared/mrjam-declarative-nix'
task_build='/workspace/shared/mrjam-declarative-build'
task_network='bridge'
if [[ "${1-}" == '--offline-container' ]]; then
  task_network='none'
  shift
fi
if [[ $# -eq 0 ]]; then
  printf '%s\n' 'LOCAL_NIX_COMMAND_REQUIRED' >&2
  exit 2
fi
docker_local() {
  env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock "$@"
}
if docker_local volume inspect "$task_volume" >/dev/null 2>&1; then
  [[ "$(docker_local volume inspect --format '{{index .Labels "mrjam.scope"}}' "$task_volume")" == 'local-declarative-synthetic' ]] || {
    printf '%s\n' 'LOCAL_NIX_VOLUME_COLLISION' >&2
    exit 2
  }
else
  docker_local volume create --label mrjam.scope=local-declarative-synthetic "$task_volume" >/dev/null
fi
mkdir -p "$task_output" "$task_build"
task_ca="${CODEX_PROXY_CERT:-/etc/ssl/certs/ca-certificates.crt}"
exec env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host=unix:///var/run/docker.sock run --rm --init \
  --label mrjam.scope=local-declarative-synthetic \
  --network "$task_network" --cpus=2 --memory=4g --pids-limit=1024 \
  --security-opt no-new-privileges \
  --mount "type=volume,src=$task_volume,dst=/nix" \
  --mount "type=bind,src=$task_root,dst=$task_root,readonly" \
  --mount "type=bind,src=/workspace/mrjam-validation,dst=/workspace/mrjam-validation,readonly" \
  --mount "type=bind,src=$task_output,dst=$task_output" \
  --mount "type=bind,src=$task_build,dst=$task_build,readonly" \
  --mount "type=bind,src=$task_ca,dst=/run/mrjam-public-ca.pem,readonly" \
  --env NIX_SSL_CERT_FILE=/run/mrjam-public-ca.pem \
  --env SSL_CERT_FILE=/run/mrjam-public-ca.pem \
  --env 'NIX_CONFIG=experimental-features = nix-command flakes
sandbox = false
max-jobs = 1
cores = 2
ssl-cert-file = /run/mrjam-public-ca.pem' \
  --workdir "$task_root" --entrypoint /bin/sh "$task_image" -c 'exec "$@"' sh "$@"
