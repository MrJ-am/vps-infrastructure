{ pkgs ? import ../forgejo/locked-toolchain.nix { } }:
let
  package = import ./bootstrap.nix { inherit pkgs; };
  path = pkgs.lib.makeBinPath [ package pkgs.bash pkgs.git pkgs.nix pkgs.coreutils pkgs.curl pkgs.nodejs ];
in pkgs.runCommand "mrjam-continuous-delivery-services" { } ''
  mkdir -p "$out"
  cat > "$out/mrjam-ci.service" <<'UNIT'
  [Unit]
  Description=MRJ.am Forgejo Actions runner
  After=network-online.target forgejo.service
  Wants=network-online.target
  [Service]
  Type=simple
  DynamicUser=yes
  StateDirectory=mrjam-ci
  StateDirectoryMode=0700
  WorkingDirectory=/var/lib/mrjam-ci
  Environment=HOME=/var/lib/mrjam-ci
  Environment=PATH=${path}
  LoadCredential=runner-token:/etc/mrjam-ci/runner-token
  LoadCredential=source-token:/etc/mrjam-ci/source-token
  ExecStart=${pkgs.forgejo-runner}/bin/forgejo-runner --config /etc/mrjam-ci/runner.json daemon
  Restart=on-failure
  RestartSec=3
  TimeoutStopSec=90min
  NoNewPrivileges=yes
  ProtectSystem=strict
  ProtectHome=yes
  PrivateTmp=yes
  InaccessiblePaths=-/var/lib/postgresql -/var/lib/forgejo -/var/lib/kanidm -/var/backup -/var/lib/etp-carnet -/var/lib/mrjam-worker-credentials -/var/lib/mrjam-ci-credentials
  [Install]
  WantedBy=multi-user.target
  UNIT
  cat > "$out/mrjam-delivery.service" <<'UNIT'
  [Unit]
  Description=MRJ.am delivery from successful Forgejo main builds
  After=network-online.target nginx.service forgejo.service mrjam-delivery-restore.service
  Wants=network-online.target
  [Service]
  Type=simple
  StateDirectory=mrjam-delivery
  StateDirectoryMode=0755
  LoadCredential=source-token:/etc/mrjam-ci/source-token
  ExecStart=${package}/bin/mrjam-delivery watch
  ExecStopPost=${package}/bin/mrjam-delivery recover
  Restart=on-failure
  RestartSec=2
  [Install]
  WantedBy=multi-user.target
  UNIT
  cat > "$out/mrjam-delivery-restore.service" <<'UNIT'
  [Unit]
  Description=Restore the last delivered application routing before Nginx
  Before=nginx.service
  [Service]
  Type=oneshot
  ExecStart=${package}/bin/mrjam-delivery restore
  RemainAfterExit=yes
  [Install]
  WantedBy=multi-user.target
  UNIT
''
