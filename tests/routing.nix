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
  vision = deployed."vision.principiipetit.io";
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
assert vision.enableACME && vision.forceSSL;
assert vision.locations."/".proxyPass == "http://127.0.0.1:3001";
assert vision.locations."/".extraConfig == ''
  client_max_body_size 4k;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_set_header Authorization "";
  proxy_set_header X-Vision-Authenticated "";
'';
assert vision.locations."/api/".proxyPass == "http://127.0.0.1:3001";
assert vision.locations."/api/".extraConfig == ''
  client_max_body_size 4k;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-For $remote_addr;
  auth_basic "Vision API";
  auth_basic_user_file /var/lib/vision/auth/htpasswd;
  limit_req zone=protected_api_per_ip burst=10 nodelay;
  limit_conn protected_api_connections 10;
  proxy_set_header Authorization "";
  proxy_set_header X-Vision-Authenticated "1";
  error_page 401 = @vision-authentication-required;
'';
assert vision.locations."= /healthz".return == "404";
assert vision.locations."@vision-authentication-required".extraConfig == ''
  default_type application/json;
  add_header Cache-Control "no-store" always;
  add_header WWW-Authenticate 'Basic realm="Vision API", charset="UTF-8"' always;
  return 401 '{"error":"authentication_required","message":"HTTP Basic authentication is required."}';
'';
{ mathevalPreserved = true; visionProtected = true; additionalProjectIsolated = true; }
