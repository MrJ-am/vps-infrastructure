{ lib, stdenv, python3, bash, coreutils, systemd, nix }:
let
  runtime = builtins.toJSON {
    python = "${python3}/bin/python3";
    systemd_run = "${systemd}/bin/systemd-run";
    systemctl = "${systemd}/bin/systemctl";
    nix = "${nix}/bin/nix";
  };
in
assert lib.versionAtLeast python3.version "3.11";
assert stdenv.hostPlatform.system == "x86_64-linux";
stdenv.mkDerivation {
  name = "mrjam-observe-services-v2";
  outputs = [ "out" "tests" ];
  inherit runtime; passAsFile = [ "runtime" ];
  nativeBuildInputs = [ python3 ];
  preferLocalBuild = true; allowSubstitutes = false;
  dontUnpack = true;
  buildPhase = ''
    cp ${./confinement.c} confinement.c
    cp ${./confinement.h} confinement.h
    cp ${./broker.c} broker.c
    cp ${./broker.h} broker.h
    substitute ${./launch.c} launch.c --replace-fail @python@ ${python3}/bin/python3 \
      --replace-fail @collector@ "$out/libexec/collect.py"
    $CC -O2 -Wall -Wextra -Werror -c confinement.c -o confinement.o
    $CC -O2 -Wall -Wextra -Werror -c broker.c -o broker.o
    $CC -O2 -Wall -Wextra -Werror launch.c confinement.o broker.o -o collect-confined
    $CC -O2 -Wall -Wextra -Werror -I. ${./probe.c} confinement.o broker.o -o confinement-probe
    $CC -O2 -Wall -Wextra -Werror -I. ${./broker-probe.c} broker.o -o broker-probe
    $CC -O2 -Wall -Wextra -Werror ${./victim.c} -o synthetic-victim
  '';
  installPhase = ''
    mkdir -p "$out/bin" "$out/libexec" "$tests/bin"
    cp ${./observe.py} "$out/libexec/observe.py"
    cp ${./collect.py} "$out/libexec/collect.py"
    cp ${./contract.py} "$out/libexec/contract.py"
    cp ${./validate_report.py} "$out/libexec/validate_report.py"
    cp ${../bootstrap-observation/bounded.py} "$out/libexec/bounded.py"
    cp "$runtimePath" "$out/libexec/runtime.json"
    install -m 0555 collect-confined "$out/libexec/collect-confined"
    install -m 0555 confinement-probe broker-probe synthetic-victim "$tests/bin/"
    printf '#!${bash}/bin/bash -p\nexec ${coreutils}/bin/env -i LANG=C LC_ALL=C ${python3}/bin/python3 -I -S %s/libexec/observe.py "$@"\n' "$out" > "$out/bin/mrjam-observe-services"
    chmod 0555 "$out/bin/mrjam-observe-services"
  '';
}
