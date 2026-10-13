;;; Reproduction depuis le graphe central, aucun serveur de développement exposé.
(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(asdf:load-system "mrjam-metier")
(mrjam-native:initialiser-crypto (uiop:getenv "MRJAM_LIBCRYPTO"))
(mrjam-native:initialiser-sqlite (uiop:getenv "MRJAM_LIBSQLITE"))
(mrjam-native:initialiser-postgresql (uiop:getenv "MRJAM_LIBPQ"))
(load (merge-pathnames "audition-oidc.lisp" *load-truename*))
(in-package #:mrjam-audition-oidc-tests)
(initialiser)
(format t "~&AUDITION-OIDC PRET~%") (finish-output)
(loop for commande = (read-line *standard-input* nil nil) while commande do
  (handler-case
    (progn
      (cond ((equal commande "debut") (debut)) ((equal commande "retour") (retour))
            ((equal commande "preparer") (preparer)) ((equal commande "seance") (seance))
            ((equal commande "reprendre") (reprendre)) (t (error "Phase inconnue")))
      (sauver) (format t "~&AUDITION-OIDC OK ~A~%" commande) (finish-output))
    (error (e)
      ;; Les valeurs privées, la pile et les corps HTTP ne sont jamais imprimés.
      (format t "~&AUDITION-OIDC ECHEC ~A phase ~A assertion ~D~A~%" (type-of e) commande (1+ *assertions*)
        (if (typep e 'file-error) (concatenate 'string " fichier " (file-namestring (file-error-pathname e))) ""))
      (finish-output) (uiop:quit 1))))
