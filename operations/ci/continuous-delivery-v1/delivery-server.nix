# Protected packaging recipe: copies the already verified ELF without patching
# or recompiling it. The caller must separately verify admission and signature.
{ pkgs ? import ../../forgejo/locked-toolchain.nix {}, rawServer, expectedSha256, expectedBytes, proposal }:
assert builtins.match "[0-9a-f]{64}" expectedSha256 != null;
assert builtins.match "[0-9a-f]{64}" proposal != null;
assert builtins.isInt expectedBytes && expectedBytes>0 && expectedBytes<=67108864;
pkgs.runCommand "mrjam-delivery-server-${builtins.substring 0 12 proposal}" {
  nativeBuildInputs=[pkgs.python3 pkgs.patchelf pkgs.makeWrapper];
  allowedReferences=["out" pkgs.glibc pkgs.stdenv.cc.cc.lib pkgs.bashNonInteractive];
} ''
  mkdir -p "$out/bin" "$out/libexec"
  cp ${rawServer} "$out/libexec/mrjam-server"
  chmod 0555 "$out/libexec/mrjam-server"
  makeWrapper "$out/libexec/mrjam-server" "$out/bin/mrjam-server" \
    --set LD_LIBRARY_PATH '${pkgs.lib.makeLibraryPath [pkgs.glibc pkgs.stdenv.cc.cc.lib]}' \
    --unset LD_PRELOAD --unset LD_AUDIT
  python3 -I -S - "$out" <<'PY'
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);executable=root/'libexec/mrjam-server';raw=executable.read_bytes()
assert len(raw)==${toString expectedBytes} and hashlib.sha256(raw).hexdigest()=='${expectedSha256}'
assert raw[:7]==b'\x7fELF\x02\x01\x01' and int.from_bytes(raw[18:20],'little')==62
def inspect(option):
    return subprocess.check_output(['${pkgs.patchelf}/bin/patchelf',option,str(executable)]).decode().strip()
assert inspect('--print-interpreter')=='${pkgs.glibc}/lib/ld-linux-x86-64.so.2'
assert inspect('--print-rpath')==""
assert set(inspect('--print-needed').splitlines())=={'libgcc_s.so.1','libm.so.6','libc.so.6','ld-linux-x86-64.so.2'}
manifest={'schema_version':1,'artifact':'byte-preserving-rust-server-package',
          'source_proposal_sha256':'${proposal}','deployment_authorized':False,
          'qualification':'content-and-runtime-libraries-only',
          'signed_payload_location':'libexec/mrjam-server',
          'payload_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                            for name in ('bin/mrjam-server','libexec/mrjam-server')}}
(root/'artifact.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
PY
''
