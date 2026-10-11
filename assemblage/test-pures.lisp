(load (merge-pathnames "charger.lisp" *load-truename*))
(asdf:load-system "matheval/tests")
(unless (uiop:symbol-call :matheval-tests :verifier)
  (error "Échec des contrôles purs Matheval."))
