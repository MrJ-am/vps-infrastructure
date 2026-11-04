{ pkgs ? import ../../forgejo/locked-toolchain.nix { }, bindingFile, bindingSha256 }:
assert builtins.match "[0-9a-f]{64}" bindingSha256 != null;
assert builtins.hashFile "sha256" bindingFile == bindingSha256;
let
  binding = pkgs.writeText "mrjam-first-source-binding.json" (builtins.readFile bindingFile);
  bootstrap = pkgs.callPackage ../forgejo-bootstrap/package.nix { forgejoUid = 982; forgejoGid = 982; };
in pkgs.runCommand "mrjam-first-release-governance-2" { } ''
  mkdir -p "$out/bin" "$out/libexec"
  cp ${./core.py} "$out/libexec/core.py"
  cp ${./credentials.py} "$out/libexec/credentials.py"
  cp ${../../forgejo/reconcile.py} "$out/libexec/reconcile.py"
  for operation in probe adopt; do
    substitute ${./entry.py} "$out/libexec/$operation.py" \
      --subst-var-by BINDING ${binding} \
      --subst-var-by BINDING_SHA256 ${bindingSha256} \
      --subst-var-by OPERATION "$operation" \
      --subst-var-by GIT ${pkgs.git} \
      --subst-var-by SELF "$out" \
      --subst-var-by BOOTSTRAP ${bootstrap}
  done
  cat > "$out/libexec/credential-entry.py" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import credentials
raise SystemExit(credentials.helper())
PY
  for specification in 'mrjam-first-release-sources-probe:probe' 'mrjam-first-release-governance:adopt' 'mrjam-forgejo-git-credential:credential-entry'; do
    executable="''${specification%:*}"
    script="''${specification#*:}"
    cat > "$out/bin/$executable" <<EOF
#!${pkgs.runtimeShell}
exec ${pkgs.python3}/bin/python3 -I -S -B "$out/libexec/$script.py" "\$@"
EOF
    chmod 0555 "$out/bin/$executable"
  done
''
