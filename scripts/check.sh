#!/bin/sh
set -eu
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
python3 scripts/registry.py
python3 scripts/databases.py
python3 -m unittest discover -s tests -v
if ! command -v nix-instantiate >/dev/null 2>&1; then
    echo "Contrôles Python réussis ; Nix absent, validation Nix non exécutée." >&2
    exit 2
fi
for module in hosts/hostinger/*.nix modules/*.nix apps/*.nix lib/*.nix vendor/matheval/*.nix tests/*.nix scripts/*.nix; do
    nix-instantiate --parse "$module" >/dev/null
done
nix-instantiate --eval --strict --json tests/routing.nix
nix-instantiate --eval --strict --json tests/databases.nix
printf '\n%s\n' 'Syntaxe, routage et registre PostgreSQL vérifiés ; évaluation NixOS et tests PostgreSQL en CI, construction complète encore requise sur le VPS.'
