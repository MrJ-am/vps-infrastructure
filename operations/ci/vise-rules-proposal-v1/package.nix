{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source { system = "x86_64-linux"; }
, bindingFile, bindingSha256 }:
assert builtins.hashFile "sha256" bindingFile == bindingSha256;
let
  binding = pkgs.writeText "mrjam-rules-proposal-binding.json" (builtins.readFile bindingFile);
  bootstrap = pkgs.callPackage ../../deployment/forgejo-bootstrap/package.nix { forgejoUid = 982; forgejoGid = 982; };
in pkgs.runCommand "mrjam-vise-rules-proposal-1" {} ''
  mkdir -p "$out/libexec" "$out/bin" "$out/hooks"
  cp ${./core.py} "$out/libexec/core.py"
  cp ${../rules-proposal-v1/lease.py} "$out/libexec/lease.py"
  cp ${../rules-proposal-v1/protection.py} "$out/libexec/protection.py"
  cp ${../../forgejo/reconcile.py} "$out/libexec/reconcile.py"
  cp ${../../deployment/forgejo-governance-v2/credentials.py} "$out/libexec/credentials.py"
  chmod u+w "$out/libexec/credentials.py"
  # The authenticated IPC implementation is unchanged; only the allowlist
  # narrows from the nine original repositories to the one rules repository.
  ${pkgs.python3}/bin/python3 - "$out/libexec/credentials.py" <<'PY'
import ast,sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_text();tree=ast.parse(s)
n=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NAMES' for t in n.targets))
lines=s.splitlines(True);lines[n.lineno-1:n.end_lineno]=['NAMES = frozenset(("mrjam-validation",))\n'];p.write_text("".join(lines))
PY
  for pair in ${./entry.py}:entry ${./pre-push.py}:pre-push; do
    source="''${pair%:*}"; target="''${pair#*:}"
    substitute "$source" "$out/libexec/$target.py" \
      --subst-var-by BINDING ${binding} --subst-var-by BINDING_SHA256 ${bindingSha256} \
      --subst-var-by BOOTSTRAP ${bootstrap} --subst-var-by GIT ${pkgs.git} --subst-var-by SELF "$out"
  done
  cat > "$out/libexec/credential-entry.py" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import credentials
raise SystemExit(credentials.helper())
PY
  for pair in bin/mrjam-open-rules-proposal:entry bin/mrjam-rules-proposal-credential:credential-entry hooks/pre-push:pre-push; do
    target="''${pair%:*}"; source="''${pair#*:}"
    cat > "$out/$target" <<EOF
#!${pkgs.runtimeShell}
exec ${pkgs.python3}/bin/python3 -I -S -B "$out/libexec/$source.py" "\$@"
EOF
    chmod 0555 "$out/$target"
  done
''
