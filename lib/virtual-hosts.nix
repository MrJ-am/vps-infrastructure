projects:
let
  sites = builtins.attrValues projects;
  hostEntries = site: [ {
    name = site.domain;
    value = {
      enableACME = true;
      forceSSL = true;
      locations = {
        "${site.prefix}/" = {
          # Sans slash terminal : conserver le préfixe attendu par l'application.
          proxyPass = "http://127.0.0.1:${toString site.port}";
          extraConfig = ''
            client_max_body_size ${site.maxBodySize};
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $remote_addr;
          '';
        };
      } // (if site.prefix != "" then {
        "= /".return = "308 ${site.prefix}/";
        "= ${site.prefix}".return = "308 ${site.prefix}/";
      } else {});
    };
  } ] ++ map (alias: {
    name = alias;
    value = { enableACME = true; forceSSL = true; globalRedirect = site.domain; };
  }) site.aliases;
in builtins.listToAttrs (builtins.concatMap hostEntries sites)
