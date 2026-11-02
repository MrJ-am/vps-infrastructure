{ pkgs ? import ../forgejo/locked-toolchain.nix { } }:
pkgs.runCommand "mrjam-resolver-update-001" { } ''
  mkdir -p "$out/bin" "$out/libexec"
  cp ${./configuration_update.py} "$out/libexec/configuration_update.py"
  cp ${./generation.py} "$out/libexec/generation.py"
  cp ${./resolver_update_adapter.py} "$out/libexec/resolver_update_adapter.py"
  cat > "$out/libexec/entry.py" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import resolver_update_adapter
raise SystemExit(resolver_update_adapter.main())
PY
  cat > "$out/bin/mrjam-resolver-update" <<EOF
#!${pkgs.runtimeShell}
exec ${pkgs.python3}/bin/python3 -I -S -B "$out/libexec/entry.py" "\$@"
EOF
  chmod 0555 "$out/bin/mrjam-resolver-update"
''
