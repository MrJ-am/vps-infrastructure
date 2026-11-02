# Immutable, read-only helpers selected by the separate sealed backend manifest.
# No shell entrypoint, arguments, network activity or host state access at build.
{ pkgs }:
pkgs.runCommand "mrjam-first-release-read-only-probes-1" { } ''
  mkdir -p "$out/libexec"
  install -m0444 ${./credentials/probe-standalone.py} "$out/libexec/probe-standalone.py"
  install -m0444 ${./preflight_obligations.py} "$out/libexec/preflight_obligations.py"
  install -m0444 ${./forgejo_sso_probe.py} "$out/libexec/forgejo_sso_probe.py"
''
