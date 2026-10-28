# Les chemins sont inscrits dans l'en-tête du lanceur pendant preCheck.
# Ils restent disponibles lorsque proc_open remplace entièrement l'environnement.
for php_filter_test_argument do
  case "$php_filter_test_argument" in
    extension=filter|extension=filter.so|extension=*/filter.so)
      exec "$php_filter_test_cgi" "$@"
      ;;
  esac
done
exec "$php_filter_test_cgi" -d "extension=$php_filter_test_module" "$@"
