;;; Image de qualification isolée ; aucune bibliothèque OIDC ni transport de dev
;;; n'est requis pour les unités Audition. Le graphe produit reste central.
(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(asdf:load-system "mrjam-audition")
(mrjam-native:initialiser-crypto (or (uiop:getenv "MRJAM_LIBCRYPTO") "/usr/lib/x86_64-linux-gnu/libcrypto.so.3"))
(mrjam-native:initialiser-postgresql (or (uiop:getenv "MRJAM_LIBPQ") "/usr/lib/x86_64-linux-gnu/libpq.so.5"))
