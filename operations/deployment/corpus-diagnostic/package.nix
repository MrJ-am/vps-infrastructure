{ pkgs ? import /nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source {} }:
let
  rust = builtins.storePath /nix/store/2va2x1g4ncjhaih1dk0zxvi97s832pw9-mrjam-rust-toolchain-1.99.1;
  inputs = builtins.storePath /nix/store/z0gvz1ynawnkvrrlh2c69x3l255jf0rd-mrjam-pinned-build-inputs;
  bank = builtins.storePath /nix/store/pdaay31fv76dxgmp1ar4xwhnbhb6fwyp-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a-mateval;
in assert builtins.hashFile "sha256" ./src/types.rs == "aed36e3ab6058d6756f3e8a6198b5a5df4c4af32e5d1eeef3f95eeed4312674c";
assert builtins.hashFile "sha256" (bank + "/data/bank.json") == "247e5a96f387fe87a183c07274139cd32f957b8ca54c9ca07257b6ee208bf480";
pkgs.stdenv.mkDerivation {
  pname = "mrjam-mateval-corpus-classifier";
  version = "1";
  src = pkgs.lib.cleanSourceWith {
    src = ./.;
    filter = path: type: type == "directory" || builtins.elem (baseNameOf path)
      [ "Cargo.toml" "Cargo.lock" "main.rs" "types.rs" ];
  };
  nativeBuildInputs = [ rust ];
  buildPhase = ''
    runHook preBuild
    export CARGO_HOME="$TMPDIR/cargo-home"
    export CARGO_NET_OFFLINE=true
    export RUSTFLAGS="--remap-path-prefix=${inputs}=/reviewed-inputs --remap-path-prefix=${bank}=/public-assets"
    cargo build --release --frozen --offline -j2 \
      --config 'source.crates-io.replace-with="reviewed-vendor"' \
      --config 'source.reviewed-vendor.directory="${inputs}/cargo-vendor"'
    runHook postBuild
  '';
  installPhase = ''
    install -Dm755 target/release/mrjam-mateval-corpus-classifier "$out/bin/mrjam-mateval-corpus-classifier"
  '';
  disallowedReferences = [ rust inputs bank ];
}
