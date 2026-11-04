{ pkgs ? import ../../forgejo/locked-toolchain.nix { }, forgejoUid ? 982, forgejoGid ? 982 }:
let
  locked = import ../../forgejo/locked-toolchain.nix { };
in assert locked.forgejo.version == "17.0.1";
assert builtins.isInt forgejoUid && forgejoUid > 0 && forgejoUid < 65534;
assert builtins.isInt forgejoGid && forgejoGid > 0 && forgejoGid < 65534;
pkgs.runCommand "mrjam-forgejo-technical-bootstrap-1" { } ''
  mkdir -p "$out/bin" "$out/libexec"
  substitute ${./core.py} "$out/libexec/core.py" \
    --subst-var-by FORGEJO ${locked.forgejo} \
    --subst-var-by POSTGRES ${pkgs.postgresql_17} \
    --replace-fail 'FORGEJO_UID = 982' 'FORGEJO_UID = ${toString forgejoUid}' \
    --replace-fail 'FORGEJO_GID = 982' 'FORGEJO_GID = ${toString forgejoGid}'
  for operation in probe bootstrap cleanup; do
    substitute ${./entry.py} "$out/libexec/$operation.py" --subst-var-by OPERATION "$operation"
    cat > "$out/bin/mrjam-forgejo-$operation" <<EOF
#!${pkgs.runtimeShell}
exec ${pkgs.python3}/bin/python3 -I -S -B "$out/libexec/$operation.py" "\$@"
EOF
    chmod 0555 "$out/bin/mrjam-forgejo-$operation"
  done
''
