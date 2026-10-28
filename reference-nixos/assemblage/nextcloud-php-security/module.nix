{ lib, pkgs, ... }:
let
  # Même branche PHP 8.4 et même Nixpkgs ; publication officielle du 21 octobre.
  # Les surcharges PHP Nixpkgs propagent aussi la source à ses extensions.
  patched = pkgs.php84.overrideAttrs (_: {
    version = "8.4.27";
    src = pkgs.fetchurl {
      url = "https://www.php.net/distributions/php-8.4.27.tar.bz2";
      hash = "sha256-slMKh3xyL0sIyeF0owywi6wrfhkD7m6eMV8KqfX4LCQ=";
    };
  });
in {
  services.nextcloud.phpPackage = lib.mkForce (patched.buildEnv {
    extensions = { enabled, ... }: map (extension:
      if extension.extensionName != "filter" then extension else
        extension.overrideAttrs (old: {
          # Les nouveaux tests OOM lancent php-cgi -n. Dans Nix, filter est un
          # module partagé : le sous-processus doit le charger explicitement.
          # Aucun PHPT modifié, supprimé ou désactivé.
          preCheck = (old.preCheck or "") + ''
            test -f "$PWD/modules/filter.so"
            php_filter_test_wrapper="$TMPDIR/php-cgi-filter-test"
            printf '#!%s\nphp_filter_test_module=%q\nphp_filter_test_cgi=%q\n' \
              "${pkgs.runtimeShell}" "$PWD/modules/filter.so" \
              "${patched.unwrapped}/bin/php-cgi" > "$php_filter_test_wrapper"
            cat ${./filter-test-cgi.sh} >> "$php_filter_test_wrapper"
            chmod 700 "$php_filter_test_wrapper"
            export TEST_PHP_CGI_EXECUTABLE="$php_filter_test_wrapper"
          '';
        })
    ) enabled;
  });
}
