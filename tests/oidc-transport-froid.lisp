;;; Reproduction depuis les sources, dans un processus de test sans état acquis.
(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(load (merge-pathnames "../assemblage/oidc/charger-dependances.lisp" *load-truename*))
(asdf:load-asd (merge-pathnames "../mrjam-oidc.asd" *load-truename*))
(asdf:load-system "mrjam-oidc/transport")
(assert (null ironclad::*os-prng-stream*))
(mrjam-native:initialiser-crypto (or (uiop:getenv "MRJAM_LIBCRYPTO") (error "Libcrypto verrouillé requis.")))
(asdf:test-system "mrjam-oidc/transport")
(format t "~&Qualification du transport OIDC en image propre réussie.~%")
