(load (merge-pathnames "charger.lisp" *load-truename*))
(asdf:load-system "matheval/tests")
(unless (uiop:symbol-call :matheval-tests :verifier)
  (error "Échec des contrôles purs Matheval."))
(let* ((racine (uiop:pathname-parent-directory-pathname
                 (uiop:pathname-directory-pathname *load-truename*)))
       (atelier (uiop:ensure-directory-pathname
                  (or (uiop:getenv "MRJAM_ATELIER")
                      (namestring (uiop:pathname-parent-directory-pathname racine))))))
  (load (merge-pathnames "tests/provenance-regressions.lisp" racine))
  (let ((fixtures (uiop:symbol-call :mrjam-regressions :verifier-provenance racine)))
    (load (merge-pathnames "tests/matheval-differentiel.lisp" racine))
    (uiop:symbol-call :matheval-differentiel :verifier
                     (merge-pathnames "matheval.json" fixtures)
                     (merge-pathnames "M-moire/research/bank.json" atelier))))
