;;; Qualification reproductible séparée ; aucune image interactive faisant autorité.
(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(load (merge-pathnames "../assemblage/oidc/charger-dependances.lisp" *load-truename*))
(asdf:load-asd (merge-pathnames "../mrjam-oidc.asd" *load-truename*))
(asdf:load-system "mrjam-oidc")
;; Le chargement des bibliothèques ne doit ouvrir ni aléa, socket ni données.
(assert (null ironclad::*os-prng-stream*))
(mrjam-native:initialiser-crypto (or (uiop:getenv "MRJAM_LIBCRYPTO") (error "Libcrypto verrouillé requis.")))
(assert (equal (mrjam-native:sha256 "abc")
               "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))
(asdf:test-system "mrjam-oidc")
(format t "~&Qualification OIDC dans une image propre réussie.~%")
