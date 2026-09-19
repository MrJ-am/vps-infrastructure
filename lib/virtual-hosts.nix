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
        proxy_set_header Authorization "";
        proxy_set_header X-Vision-Authenticated "1";
        error_page 401 = @${site.service}-authentication-required;
      '';
    };
    "@${site.service}-authentication-required" = {
      extraConfig = ''
        default_type application/json;
        add_header Cache-Control "no-store" always;
        add_header WWW-Authenticate 'Basic realm="${site.auth.realm}", charset="UTF-8"' always;
        return 401 '{"error":"authentication_required","message":"HTTP Basic authentication is required."}';
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
    };
  } ] ++ map (alias: {
    name = alias;
    value = { enableACME = true; forceSSL = true; globalRedirect = site.domain; };
  }) site.aliases;
in builtins.listToAttrs (builtins.concatMap hostEntries sites)
