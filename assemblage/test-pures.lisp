(load (merge-pathnames "charger.lisp" *load-truename*))
(asdf:load-system "matheval/tests")
(unless (uiop:symbol-call :matheval-tests :verifier) (uiop:quit 1))
