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
  vision = deployed."vision.mrj.am";
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
assert vision.extraConfig == ''
  add_header Strict-Transport-Security "max-age=31536000" always;
'';
assert vision.locations."/".proxyPass == "http://127.0.0.1:3001";
assert vision.locations."/".extraConfig == ''
  client_max_body_size 64k;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_set_header Authorization "";
  proxy_set_header X-Vision-Authenticated "";
  proxy_set_header X-Vision-Browser "";
  proxy_set_header X-Mrj-User "";
'';
assert vision.locations."/api/".proxyPass == "http://127.0.0.1:3001";
assert vision.locations."/api/".extraConfig == ''
  client_max_body_size 64k;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-For $remote_addr;
  auth_basic "Vision API";
  auth_basic_user_file /var/lib/vision/auth/htpasswd;
  limit_req zone=protected_api_per_ip burst=10 nodelay;
  limit_conn protected_api_connections 10;
  limit_req_status 429;
  limit_conn_status 429;
  proxy_set_header Authorization "";
  proxy_set_header X-Vision-Authenticated "1";
  proxy_set_header X-Vision-Browser "";
  proxy_set_header X-Mrj-User $remote_user;
  error_page 401 = @vision-authentication-required;
  error_page 429 = @vision-rate-limited;
'';
assert vision.locations."= /healthz".return == "404";
assert vision.locations."@vision-authentication-required".extraConfig == ''
  default_type application/json;
  add_header Cache-Control "no-store" always;
  add_header WWW-Authenticate 'Basic realm="Vision API", charset="UTF-8"' always;
  add_header Strict-Transport-Security "max-age=31536000" always;
  add_header X-Content-Type-Options "nosniff" always;
  return 401 '{"error":"authentication_required","message":"HTTP Basic authentication is required."}';
'';
assert vision.locations."@vision-rate-limited".extraConfig == ''
  default_type application/json;
  add_header Cache-Control "no-store" always;
  add_header Retry-After "1" always;
  add_header Strict-Transport-Security "max-age=31536000" always;
  add_header X-Content-Type-Options "nosniff" always;
  return 429 '{"error":"rate_limited","message":"Too many requests."}';
'';
{ mathevalPreserved = true; visionProtected = true; additionalProjectIsolated = true; }

