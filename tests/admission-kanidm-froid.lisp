;;; Qualification depuis les sources, sans MCP/Swank ni données de production.
(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(asdf:load-system "mrjam-metier")
(mrjam-native:initialiser-crypto (uiop:getenv "MRJAM_LIBCRYPTO"))
(mrjam-native:initialiser-sqlite (uiop:getenv "MRJAM_LIBSQLITE"))
(mrjam-native:initialiser-postgresql (uiop:getenv "MRJAM_LIBPQ"))
(load (uiop:getenv "MRJAM_ADMISSION_FORMES"))
