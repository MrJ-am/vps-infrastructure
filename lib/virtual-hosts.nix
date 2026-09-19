projects:
let
  sites = builtins.attrValues projects;
  proxyHeaders = site: ''
    client_max_body_size ${site.maxBodySize};
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
  '';
  publicLocation = site: {
    # Sans slash terminal : conserver le préfixe attendu par l'application.
    proxyPass = "http://127.0.0.1:${toString site.port}";
    extraConfig = proxyHeaders site + (if site ? auth then ''
      proxy_set_header Authorization "";
      proxy_set_header X-Vision-Authenticated "";
    '' else "");
  };
  protectedLocations = site: if site ? auth then {
    "${site.auth.prefix}" = {
      proxyPass = "http://127.0.0.1:${toString site.port}";
      extraConfig = proxyHeaders site + ''
        auth_basic "${site.auth.realm}";
        auth_basic_user_file ${site.auth.basicUserFile};
        limit_req zone=protected_api_per_ip burst=10 nodelay;
        limit_conn protected_api_connections 10;
        limit_req_status 429;
        limit_conn_status 429;
        proxy_set_header Authorization "";
        proxy_set_header X-Vision-Authenticated "1";
        error_page 401 = @${site.service}-authentication-required;
        error_page 429 = @${site.service}-rate-limited;
      '';
    };
    "@${site.service}-authentication-required" = {
      extraConfig = ''
        default_type application/json;
        add_header Cache-Control "no-store" always;
        add_header WWW-Authenticate 'Basic realm="${site.auth.realm}", charset="UTF-8"' always;
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        return 401 '{"error":"authentication_required","message":"HTTP Basic authentication is required."}';
      '';
    };
    "@${site.service}-rate-limited" = {
      extraConfig = ''
        default_type application/json;
        add_header Cache-Control "no-store" always;
        add_header Retry-After "1" always;
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        return 429 '{"error":"rate_limited","message":"Too many requests."}';
      '';
    };
    "= ${site.privateHealthPath}".return = "404";
  } else {};
  hostEntries = site: [ {
    name = site.domain;
    value = {
      enableACME = true;
      forceSSL = true;
      locations = {
        "${site.prefix}/" = publicLocation site;
      } // protectedLocations site // (if site.prefix != "" then {
        "= /".return = "308 ${site.prefix}/";
        "= ${site.prefix}".return = "308 ${site.prefix}/";
      } else {});
    } // (if site ? auth then {
      extraConfig = ''
        add_header Strict-Transport-Security "max-age=31536000" always;
      '';
    } else {});
  } ] ++ map (alias: {
    name = alias;
    value = { enableACME = true; forceSSL = true; globalRedirect = site.domain; };
  }) site.aliases;
in builtins.listToAttrs (builtins.concatMap hostEntries sites)
