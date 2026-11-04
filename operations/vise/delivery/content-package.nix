# Fixed recipe: no candidate Nix or compilation. Caller must verify admission.
{ artifactRoot, proposal, serverSha256, serverBytes, frontendSha256
, pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
assert builtins.match "[0-9a-f]{64}" frontendSha256 != null;
let
  server=import ../../ci/continuous-delivery-v1/delivery-server.nix {
    inherit pkgs proposal;rawServer=artifactRoot+"/server";
    expectedSha256=serverSha256;expectedBytes=serverBytes;
  };
in pkgs.runCommand "mrjam-vise-delivery-content-${builtins.substring 0 12 proposal}" {
  nativeBuildInputs=[pkgs.python3];
  passthru={inherit server;};
} ''
  mkdir -p "$out/dist"
  ln -s ${server}/bin/mrjam-server "$out/server"
  cp ${./package_content.py} package_content.py
  python3 -I -S - "$PWD" "$out" <<'PY'
import hashlib,json,pathlib,sys
sys.path.insert(0,sys.argv[1]);import package_content as P
raw=pathlib.Path('${artifactRoot}/frontend.tar').read_bytes()
files=P.frontend(raw,'${frontendSha256}');root=pathlib.Path(sys.argv[2])
for name,data in sorted(files.items()):
    path=root/'dist'/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(data)
    path.chmod(0o444)
manifest={'schema_version':1,'profile':'vise-v1','proposal_sha256':'${proposal}',
    'server':'${server}','server_sha256':'${serverSha256}',
    'frontend_archive_sha256':'${frontendSha256}',
    'frontend_files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
    'deployment_authorized':False}
(root/'artifact.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
PY
''
