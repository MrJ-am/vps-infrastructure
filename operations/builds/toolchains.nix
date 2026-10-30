{ lib, stdenv, fetchurl, autoPatchelfHook, zlib }:
let
  lock = builtins.fromJSON (builtins.readFile ./toolchains.lock.json);
in
assert lib.assertMsg (stdenv.hostPlatform.system == lock.target)
  "The official build tool archives are pinned for x86_64-linux only.";
{
  rust = stdenv.mkDerivation {
    pname = "mrjam-rust-toolchain";
    inherit (lock.rust) version;
    src = fetchurl { inherit (lock.rust) url sha256; };
    nativeBuildInputs = [ autoPatchelfHook ];
    buildInputs = [ stdenv.cc.cc.lib zlib ];
    dontConfigure = true;
    dontBuild = true;
    installPhase = ''
      runHook preInstall
      ./install.sh --prefix="$out" --disable-ldconfig \
        --components=rustc,cargo,rust-std-x86_64-unknown-linux-gnu,rustfmt-preview,clippy-preview
      runHook postInstall
    '';
    doInstallCheck = true;
    installCheckPhase = ''
      test "$("$out/bin/rustc" --version | cut -d' ' -f2)" = '${lock.rust.version}'
      test "$("$out/bin/cargo" --version | cut -d' ' -f2)" = '${lock.rust.version}'
    '';
    meta = { platforms = [ lock.target ]; license = [ lib.licenses.mit lib.licenses.asl20 ]; };
  };
  node = stdenv.mkDerivation {
    pname = "mrjam-node-build-tool";
    inherit (lock.node) version;
    src = fetchurl { inherit (lock.node) url sha256; };
    nativeBuildInputs = [ autoPatchelfHook ];
    buildInputs = [ stdenv.cc.cc.lib ];
    dontConfigure = true;
    dontBuild = true;
    installPhase = ''
      runHook preInstall
      install -Dm755 bin/node "$out/bin/node"
      install -Dm644 LICENSE "$out/share/doc/node/LICENSE"
      runHook postInstall
    '';
    doInstallCheck = true;
    installCheckPhase = ''
      test "$("$out/bin/node" --version)" = 'v${lock.node.version}'
    '';
    meta = { platforms = [ lock.target ]; license = lib.licenses.mit; };
  };
}
