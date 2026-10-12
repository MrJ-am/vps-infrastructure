;;; Qualification depuis sources/FASL, aucune image interactive remplacée.
(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(load (merge-pathnames "../assemblage/oidc/charger-dependances.lisp" *load-truename*))
(asdf:load-asd (merge-pathnames "../mrjam-oidc.asd" *load-truename*))
(asdf:load-system "mrjam-oidc/kanidm-tests")
(assert (null ironclad::*os-prng-stream*))
(mrjam-native:initialiser-crypto (or (uiop:getenv "MRJAM_LIBCRYPTO") (error "Libcrypto verrouillé requis.")))
(let ((n (uiop:symbol-call :mrjam-oidc-kanidm-tests :verifier
           (or (uiop:getenv "MRJAM_KANIDM_FIXTURE") (error "Fixture native requise.")))))
  (assert (and (integerp n) (>= n 15))))
(format t "~&Qualification OIDC Kanidm en image propre réussie.~%")
