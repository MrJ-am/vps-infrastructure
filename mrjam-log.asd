(asdf:defsystem "mrjam-log"
  :description "Sessions applicatives Kanidm, hors identité et secrets maîtres."
  :depends-on ("mrjam-oidc/transport")
  :serial t
  :components ((:file "lisp/identite/log-package") (:file "lisp/identite/log-sessions")
               (:file "lisp/identite/log-oauth")))

(asdf:defsystem "mrjam-log/tests"
  :depends-on ("mrjam-log")
  :components ((:file "tests/log-sessions"))
  :perform (asdf:test-op (o s)
             (declare (ignore o s))
             (assert (uiop:symbol-call :mrjam-log-tests :verifier))))

(asdf:defsystem "mrjam-log/kanidm-tests"
  :depends-on ("mrjam-log/tests" "mrjam-metier")
  :components ((:file "tests/log-kanidm")))
