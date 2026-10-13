;;; Reproductibilité des assertions depuis les sources, aucune image interactive concurrente.
(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(load (merge-pathnames "../assemblage/oidc/charger-dependances.lisp" *load-truename*))
(asdf:load-asd (merge-pathnames "../mrjam-oidc.asd" *load-truename*))
(asdf:load-asd (merge-pathnames "../mrjam-log.asd" *load-truename*))
(asdf:load-asd (merge-pathnames "mrjam-log-parcours-tests.asd" *load-truename*))
(asdf:load-system "mrjam-log-parcours-tests")
(loop for form = (read *standard-input* nil :fin) until (eq form :fin) do
  (handler-case (eval form)
    (error (e) (format t "~&PARCOURS-ECHEC ~A~%" (type-of e)) (finish-output))))
