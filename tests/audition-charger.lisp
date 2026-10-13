;;; Image de qualification isolée ; aucune bibliothèque OIDC ni transport de dev
;;; n'est requis pour les unités Audition. Le graphe produit reste central.
(require :asdf)
(let* ((infra (uiop:pathname-parent-directory-pathname (uiop:pathname-directory-pathname *load-truename*)))
       (atelier (or (uiop:getenv "MRJAM_ATELIER") (uiop:pathname-parent-directory-pathname infra))))
  (asdf:load-asd (merge-pathnames "vision/vision.asd" atelier))
  (asdf:load-asd (merge-pathnames "mrjam-native.asd" infra))
  (asdf:load-asd (merge-pathnames "mrjam-audition.asd" infra)))
(asdf:load-system "mrjam-audition")
(mrjam-native:initialiser-crypto (or (uiop:getenv "MRJAM_LIBCRYPTO") "/usr/lib/x86_64-linux-gnu/libcrypto.so.3"))
(mrjam-native:initialiser-postgresql (or (uiop:getenv "MRJAM_LIBPQ") "/usr/lib/x86_64-linux-gnu/libpq.so.5"))
