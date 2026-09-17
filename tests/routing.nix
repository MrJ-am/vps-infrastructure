let
  generate = import ../lib/virtual-hosts.nix;
  projects = builtins.fromJSON (builtins.readFile ../projects.json);
  original = { inherit (projects) matheval; };
  current = generate original;
  deployed = generate projects;
  extended = generate (original // {
    example = { domain = "demo.example.com"; aliases = []; port = 3001; prefix = ""; maxBodySize = "1m"; };
  });
  primary = current."principiipetit.io";
in
assert builtins.attrNames current == [ "principiipetit.io" "www.principiipetit.io" ];
assert primary.enableACME && primary.forceSSL;
assert primary.locations."= /".return == "308 /matheval/";
assert primary.locations."= /matheval".return == "308 /matheval/";
assert primary.locations."/matheval/".proxyPass == "http://127.0.0.1:3000";
assert primary.locations."/matheval/".extraConfig == ''
  client_max_body_size 5m;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-For $remote_addr;
'';
assert current."www.principiipetit.io" == {
  enableACME = true; forceSSL = true; globalRedirect = "principiipetit.io";
};
assert extended."principiipetit.io" == primary;
assert deployed."principiipetit.io" == primary;
assert extended."www.principiipetit.io" == current."www.principiipetit.io";
assert extended."demo.example.com".locations."/".proxyPass == "http://127.0.0.1:3001";
assert builtins.attrNames extended."demo.example.com".locations == [ "/" ];
{ mathevalPreserved = true; additionalProjectIsolated = true; }
